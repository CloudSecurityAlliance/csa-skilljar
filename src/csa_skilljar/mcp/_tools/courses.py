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

from ...client import SkilljarClient
from .._schemas import CourseDetailOut, CourseListOut, CourseOut
from ._base import READ, translate_errors

_NOTE = ("Results are one page, not necessarily the whole catalogue. When has_more is "
         "true, call again with next_cursor. The official Skilljar MCP server cannot "
         "page at all; page_cursor and page_size are extensions here.")


# Everything get_course adds over list_courses. Kept as a tuple so the two tools
# cannot silently diverge in which attributes they surface.
_COURSE_DETAIL_KEYS = ("short_description", "long_description_html",
                       "enforce_sequential_navigation", "external_id",
                       "is_published", "lesson_count", "created_at", "modified_at")


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
