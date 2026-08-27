"""`list_courses` - the one real read in v0.0.1.

Parity note (ADR-006): the official tool accepts ONLY `filter_title` and has no
pagination at all, so a large catalogue truncates with no documented way to page.
`page_cursor` and `page_size` are our additive extension: omit them and the behaviour is
identical to the official server's.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import BatchResultOut, CourseDetailOut, CourseListOut, CourseOut
from ._base import READ, WRITE, translate_errors

_NOTE = ("Results are one page, not necessarily the whole catalogue. When has_more is "
         "true, call again with next_cursor. The official Skilljar MCP server cannot "
         "page at all; page_cursor and page_size are extensions here.")


# Everything get_course adds over list_courses. Kept as a tuple so the two tools
# cannot silently diverge in which attributes they surface.
_COURSE_DETAIL_KEYS = ("short_description", "long_description_html",
                       "enforce_sequential_navigation", "external_id",
                       "is_published", "lesson_count", "created_at", "modified_at")


# Exactly what the official server accepts. Anything else is rejected rather than
# silently dropped, so a typo is a message instead of a field that never took effect.
_COURSE_WRITE_FIELDS = frozenset({
    "title", "short_description", "long_description_html",
    "enforce_sequential_navigation", "created_by_email"})

_BATCH_NOTE = ("Rows are processed independently. A non-empty `failed` means some rows "
               "did not land - report that rather than reporting success.")


def _check_write_items(items: list[dict[str, Any]], allowed: frozenset[str], label: str,
                       *, required: tuple[str, ...] = (), needs_id: bool = False) -> None:
    """Reject locally what the API would reject with a document-level 422.

    Skilljar applies per-item isolation only AFTER the envelope parses: a schema
    violation on any ONE item rejects the WHOLE request, so forty-nine good rows are
    silently not written. Catching it here means the caller learns which item was wrong
    instead of receiving one opaque failure for the batch - and, critically, nothing is
    written, matching the API rather than being more permissive than it.
    """
    if not items:
        raise ValueError(f"{label} must contain at least one item")
    permitted = allowed | ({"id"} if needs_id else set())
    for i, attrs in enumerate(items):
        if not isinstance(attrs, dict):
            raise ValueError(f"{label}[{i}] must be an object of attributes")
        if needs_id and not attrs.get("id"):
            raise ValueError(f"{label}[{i}] needs an `id` saying which record to update")
        for field in required:
            if not attrs.get(field):
                raise ValueError(f"{label}[{i}] is missing required attribute `{field}`")
        unknown = sorted(set(attrs) - permitted)
        if unknown:
            raise ValueError(
                f"{label}[{i}] has unknown attribute(s) {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(permitted))}")


def _batch_out(envelope: dict[str, Any]) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]],
            "note": _BATCH_NOTE}


def _flatten(row: dict[str, Any]) -> CourseOut:
    attrs = row.get("attributes", {})
    out: CourseOut = {"id": row.get("id", ""), "title": attrs.get("title", "")}
    for key in ("external_id", "is_published", "lesson_count"):
        if key in attrs:
            out[key] = attrs[key]
    return out


def register_course_tools(app: MCPServer, get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_courses(filter_title: str | None = None, page_cursor: str | None = None,
                     page_size: int | None = None) -> CourseListOut:
        """List the organization's non-deleted, non-draft courses.

        Returns ONE PAGE. Check `has_more` - if it is true there are more courses than
        you can see, and you must call again with `next_cursor` before telling the user
        how many courses exist or that a course is absent.

        `filter_title` is a case-insensitive partial match on the course title. Requires
        the `courses:read` OAuth scope; if the credential lacks it this fails locally,
        naming the scope, without calling Skilljar.
        """
        if page_size is not None and page_size < 1:
            raise ValueError("page_size must be 1 or greater")
        env = get_client().list_courses(title=filter_title, cursor=page_cursor,
                                        page_size=page_size)
        out: CourseListOut = {"courses": [_flatten(r) for r in env.get("data", [])],
                              "has_more": bool(env.get("has_more")), "note": _NOTE}
        nxt = env.get("next_cursor")
        if nxt:
            out["next_cursor"] = nxt
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_course(id: str) -> CourseDetailOut:
        """Fetch one course by its Skilljar id, with its full attributes.

        Returns more than `list_courses` does - descriptions, navigation settings and
        timestamps - so prefer this when you need detail about a course you have already
        located. It does NOT return the course's lessons; use `list_lessons` with
        `filter_course_id` for those.

        `id` is the obfuscated Skilljar course id, not a title. Requires the
        `courses:read` OAuth scope. A malformed, cross-organization, soft-deleted or
        draft id is reported as not found.
        """
        row = get_client().get_course(course_id=id).get("data", {})
        attrs = row.get("attributes", {})
        out: CourseDetailOut = {"id": row.get("id", ""), "title": attrs.get("title", "")}
        for key in _COURSE_DETAIL_KEYS:
            if key in attrs:
                out[key] = attrs[key]   # type: ignore[literal-required]
        return out

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_courses(courses: list[dict[str, Any]]) -> BatchResultOut:
        """Create one or more courses. This is a BATCH operation.

        Pass a list even for a single course. Each item is an attributes object:
        `title` is required (1-500 characters); `short_description`,
        `long_description_html`, `enforce_sequential_navigation` and `created_by_email`
        are optional. Any other attribute is rejected rather than silently dropped.

        Rows are processed independently and the result reports each one, so a partial
        failure is normal: check `failed` before reporting success. `ids` holds the new
        course ids in the order they were created.

        A new course has NO lessons and is not published - creating one does not make it
        visible to anyone. Requires the `courses:write` OAuth scope.
        """
        _check_write_items(courses, _COURSE_WRITE_FIELDS, "courses", required=("title",))
        return _batch_out(get_client().create_courses(items=courses))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_courses(courses: list[dict[str, Any]]) -> BatchResultOut:
        """Update one or more existing courses. This is a BATCH operation.

        Each item needs an `id` saying which course to change, plus the attributes to
        set. This is a PARTIAL update: an attribute you omit is PRESERVED, not cleared.

        Rows are processed independently - check `failed` before reporting success. An
        id that is malformed, missing, from another organization, soft-deleted or still
        a draft comes back as a per-item `not_found`, never as a whole-batch error.

        Duplicate ids within one call are applied in order, so the last one wins.
        Requires the `courses:write` OAuth scope.
        """
        _check_write_items(courses, _COURSE_WRITE_FIELDS, "courses", needs_id=True)
        return _batch_out(get_client().update_courses(items=courses))
