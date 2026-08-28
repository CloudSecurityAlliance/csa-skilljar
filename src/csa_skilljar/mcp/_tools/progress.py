"""Learner progress — the first capability served by v1 rather than v2.

ADR-002 decides which API answers: v2 owns every capability v2 has, and v1 is used only
for what v2 lacks. This qualifies. v2's enrolment record carries score, status and dates
but **no lesson counts, no credits, no re-enrolment history** — so "how far through this
course is this learner, in lessons" is a question only v1 can answer.

Everything here needs `CSA_SKILLJAR_V1_API_KEY`, which is a separate credential from the
v2 client id and secret. Neither substitutes for the other.

Two upstream behaviours are handled here rather than passed on. Both were found by
probing the live API on 2026-08-28, and neither is in Skilljar's published v1 document:

* **Per-lesson progress does not exist.** The documented endpoint
  `/v1/users/{id}/published-courses/{id}/lessons` returns 404. No tool here claims to
  provide it, and `list_learner_progress` says what it can and cannot answer.
* **The by-id fetch resolves by the underlying course, not the publication**, so a course
  published to two domains returns the wrong one with a 200. `get_learner_progress`
  selects from the listing instead. See `V1Backend.get_learner_progress`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import (
    LearnerListOut,
    LearnerOut,
    LearnerProgressListOut,
    LearnerProgressOut,
)
from ._base import READ, translate_errors

_NO_PER_LESSON = (
    "Counts only: this says how many lessons are complete, not WHICH ones. Skilljar's "
    "v1 document describes a per-lesson endpoint, but it returns 404 on the live API, "
    "so per-lesson detail is not available through any tool here.")
_V1_NOTE = ("Served by Skilljar's v1 API, which v2 has no equivalent for - v2's "
            "enrolment record carries no lesson counts, credits or re-enrolment "
            "history.")


def _flatten(row: dict[str, Any]) -> LearnerProgressOut:
    cp = row.get("course_progress") or {}
    course = row.get("course") or {}
    out: dict[str, Any] = {"published_course_id": row.get("published_course_id", "")}
    for src, key, dst in (
            (row, "domain_name", "domain_name"),
            (row, "enrolled_at", "enrolled_at"),
            (row, "enrollment_id", "enrollment_id"),
            (course, "id", "course_id"),
            (course, "title", "course_title"),
            (course, "lesson_count", "lesson_count"),
            (course, "required_lesson_count", "required_lesson_count"),
            (cp, "completed_lesson_count", "completed_lesson_count"),
            (cp, "completed_required_lesson_count", "completed_required_lesson_count"),
            (cp, "credits_earned", "credits_earned"),
            (cp, "credit_unit_plural", "credit_unit_plural"),
            (cp, "latest_activity", "latest_activity"),
            (cp, "completed_at", "completed_at"),
            (cp, "score", "score"),
            (cp, "max_score", "max_score"),
            (cp, "success_status", "success_status")):
        if key in src:
            out[dst] = src[key]
    out["has_certificate"] = bool(row.get("certificate"))
    # A learner can be enrolled in the same published course more than once. The count
    # is surfaced because a single progress figure alongside a silent re-enrolment
    # reads as lost progress rather than a fresh attempt.
    enrolments = row.get("all_enrollments")
    if isinstance(enrolments, list):
        out["enrollment_count"] = len(enrolments)
    return cast(LearnerProgressOut, out)


def _flatten_learner(row: dict[str, Any]) -> LearnerOut:
    # The v1 listing NESTS the learner under `user`; the outer row is a summary. A
    # reader looking for `id` at the top level finds nothing at all.
    user = row.get("user") or {}
    out: dict[str, Any] = {"id": user.get("id", "")}
    for key in ("email", "first_name", "last_name"):
        if key in user:
            out[key] = user[key]
    for key in ("signed_up_at", "registration_count", "completion_count",
                "latest_activity"):
        if key in row:
            out[key] = row[key]
    return cast(LearnerOut, out)


def register_progress_tools(app: MCPServer,
                            get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_learner_progress(user_id: str) -> LearnerProgressListOut:
        """How far a learner has got in every course they are enrolled in.

        `user_id` is the learner's Skilljar id. The SAME id works in v2 - `list_students`
        returns it - so no translation is needed between the two APIs.

        Answers what v2 cannot: `completed_lesson_count` against `lesson_count`,
        `completed_required_lesson_count` against `required_lesson_count`, credits
        earned, and `latest_activity`. v2's `list_enrollments` gives score and status but
        no lesson counts at all, so "40% of the way through" is only answerable here.

        COUNTS ONLY, NOT WHICH LESSONS. Skilljar's published v1 document describes a
        per-lesson endpoint; it returns 404 on the live API, so per-lesson detail is
        unavailable through any tool here. Do not report it as merely missing data.

        `enrollment_count` above 1 means the learner enrolled more than once. Read a low
        progress figure alongside it as a fresh attempt rather than lost work.

        Not paginated - every enrolment comes back at once.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not user_id:
            raise ValueError("user_id is required - the learner's Skilljar id")
        page = get_client().list_learner_progress(user_id=user_id)
        out: LearnerProgressListOut = {
            "user_id": user_id,
            "progress": [_flatten(r) for r in page["rows"]],
            "note": f"{_V1_NOTE} {_NO_PER_LESSON}"}
        if page.get("total") is not None:
            out["total"] = page["total"]
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_learner_progress(user_id: str,
                             published_course_id: str) -> LearnerProgressOut:
        """How far one learner has got in one course on one domain.

        `user_id` is the learner's Skilljar id, the same value v2's `list_students`
        returns. `published_course_id` identifies the course ON A PARTICULAR DOMAIN. A course
        published to two domains has two of them, with separate progress, and this
        returns the one asked for.

        That distinction is load-bearing. Skilljar's own by-id endpoint
        resolves by the underlying course, not the publication, and returns a DIFFERENT
        domain's record with a 200 when a course is published more than once. This tool selects
        from the learner's full list instead, so the answer always matches the id given.

        COUNTS ONLY, NOT WHICH LESSONS - the per-lesson endpoint returns 404 upstream.

        A learner not enrolled in that published course is a not-found error, and the
        message says how many enrolments they do have.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not user_id:
            raise ValueError("user_id is required - the learner's Skilljar id")
        if not published_course_id:
            raise ValueError(
                "published_course_id is required - the course on a particular domain, "
                "not the course id. list_learner_progress shows the learner's.")
        page = get_client().get_learner_progress(
            user_id=user_id, published_course_id=published_course_id)
        return _flatten(page["rows"][0])

    @app.tool(annotations=READ)
    @translate_errors
    def find_learner(email: str) -> LearnerListOut:
        """Look up a learner by email, and get the id the progress tools need.

        Returns the learner's id plus lifetime counts v2 does not carry:
        `registration_count`, `completion_count` and `latest_activity` across the whole
        organization.

        The id returned works in BOTH APIs - the same value identifies this learner to
        v2's `get_student` and to `list_learner_progress`. Observed rather than
        documented, so worth re-checking if Skilljar ever changes its id scheme.

        Email match is exact, and an unknown address returns an empty list rather than
        an error - so an empty result does not prove the address is wrong.

        `total` is v1's own count of matches. v2 never provides a total for anything.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not email:
            raise ValueError("email is required")
        page = get_client().find_learner(email=email)
        out: LearnerListOut = {
            "learners": [_flatten_learner(r) for r in page["rows"]],
            "note": f"{_V1_NOTE} An empty list means no exact match, not a bad address."}
        if page.get("total") is not None:
            out["total"] = page["total"]
        return out
