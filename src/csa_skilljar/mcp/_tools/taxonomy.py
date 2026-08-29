"""Labels, tags and group categories — how a catalogue is organised.

v1-only. Small, and the value is in telling three similar things apart:

  label            an INTERNAL classification. Applied to courses and paths, not shown
                   to learners. What an organization uses to keep its own catalogue
                   straight.
  tag              a PUBLIC one, with a `slug`, used in catalogue URLs and filters.
                   Learners see these.
  group category   groups student GROUPS, not content. It is in this module only
                   because it is the third taxonomy, and it is gated with the group
                   tools rather than the content ones.

The label/tag distinction is the one that matters: reporting an internal label as though
a learner can see it, or a public tag as though it is private, both misdescribe the
catalogue.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import CommerceListOut
from ._base import READ, translate_errors


def _out(page: dict[str, Any], requested: int | None, note: str) -> CommerceListOut:
    out: CommerceListOut = {"rows": page["rows"], "note": note}
    if page.get("total") is not None:
        out["total"] = page["total"]
    out["page"] = requested or 1
    out["has_more"] = bool(page.get("has_more"))
    if page.get("next_page") is not None:
        out["next_page"] = page["next_page"]
    return out


def _size(n: int | None) -> int:
    size = n or 100
    if not 1 <= size <= 250:
        raise ValueError(f"page_size must be between 1 and 250; got {size}")
    return size


def register_taxonomy_tools(app: MCPServer,
                            get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_labels(page: int | None = None,
                    page_size: int | None = None) -> CommerceListOut:
        """List labels - the organization's INTERNAL classification of its content.

        Labels are not shown to learners. They are how a team keeps its own catalogue
        straight, so a label is evidence about how the organization thinks, not about
        what a customer sees.

        For the public equivalent use `list_tags`, which carries a `slug` and appears in
        catalogue URLs. Describing a label as something learners can browse is wrong in
        a way that is hard to spot.

        `list_course_labels` shows which labels are on one course.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        got = get_client().list_labels(page=page, page_size=_size(page_size))
        return _out(got, page, "Labels are INTERNAL - not shown to learners. Tags are "
                               "the public ones.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_tags(page: int | None = None,
                  page_size: int | None = None) -> CommerceListOut:
        """List tags - the PUBLIC classification learners can see and browse by.

        A tag has a `slug`, which is what appears in catalogue URLs and filters, so a tag
        is part of the customer-facing site in a way a label is not.

        For the internal equivalent use `list_labels`.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        got = get_client().list_tags(page=page, page_size=_size(page_size))
        return _out(got, page, "Tags are PUBLIC and carry a slug used in catalogue URLs. "
                               "Labels are the internal ones.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_course_labels(course_id: str) -> CommerceListOut:
        """Which internal classifications a single course has been given.

        `course_id` is the course, not a published course - labels attach to the content
        rather than to a publication, so they are the same on every domain the course
        appears on.

        These are internal: they do not affect what a learner sees.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not course_id:
            raise ValueError("course_id is required - the course, not a published course")
        got = get_client().list_course_labels(course_id=course_id)
        return _out(got, None, "Labels attach to the COURSE, so they are the same on "
                               "every domain it is published to.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_group_categories(page: int | None = None,
                              page_size: int | None = None) -> CommerceListOut:
        """List the categories used to organise student groups into families.

        This groups GROUPS, not content - which is why it is the odd one among the
        taxonomy tools. A category is what `list_groups`' `filter_category_id` accepts,
        so this is where that id comes from.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        got = get_client().list_group_categories(page=page, page_size=_size(page_size))
        return _out(got, page, "These categorise student GROUPS, not content. The ids "
                               "feed list_groups' filter_category_id.")
