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
from .._schemas import CourseListOut, CourseOut
from ._base import READ, translate_errors

_NOTE = ("Results are one page, not necessarily the whole catalogue. When has_more is "
         "true, call again with next_cursor. The official Skilljar MCP server cannot "
         "page at all; page_cursor and page_size are extensions here.")


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
