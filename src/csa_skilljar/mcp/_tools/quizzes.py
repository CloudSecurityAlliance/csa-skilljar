"""Quiz tools, including the project's first destructive operation.

Parity note (ADR-006): the official `list_quizzes` accepts `filter.name` and
`filter.updated_since` and has NO pagination; `page_cursor` / `page_size` are additive.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import BatchResultOut, QuizDetailOut, QuizListOut, QuizOut
from ._base import DESTRUCTIVE, READ, WRITE, translate_errors

ALIGNMENTS = ("left", "center", "right")

_QUIZ_FIELDS = frozenset({
    "name", "description_html", "alignment", "passing_percentage_correct",
    "max_attempts", "limit_question_count", "time_limit_seconds", "skip_start_screen",
    "randomize_questions", "randomize_answers", "require_correct_response",
    "show_question_feedback", "show_results_on_failure"})

_DETAIL_KEYS = tuple(sorted(_QUIZ_FIELDS - {"name"})) + (
    "external_id", "created_at", "modified_at")

_NOTE = ("Results are one page. When has_more is true, call again with next_cursor. "
         "The official Skilljar MCP server cannot page at all; page_cursor and page_size "
         "are extensions here.")
_BATCH_NOTE = ("Rows are processed independently. A non-empty `failed` means some rows "
               "did not land - report that rather than reporting success.")


def _batch_out(envelope: dict[str, Any]) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]], "note": _BATCH_NOTE}


def _check_quiz_items(items: list[dict[str, Any]], *, needs_id: bool) -> None:
    """Reject locally what the API rejects with a document-level 422.

    Skilljar runs check_quiz_cross_field_rules in the schema layer, so a violation on
    ANY item rejects the WHOLE request. Catching it here names the item.
    """
    if not items:
        raise ValueError("quizzes must contain at least one item")
    permitted = _QUIZ_FIELDS | ({"id"} if needs_id else set())
    for i, attrs in enumerate(items):
        if not isinstance(attrs, dict):
            raise ValueError(f"quizzes[{i}] must be an object of attributes")
        if needs_id and not attrs.get("id"):
            raise ValueError(f"quizzes[{i}] needs an `id` saying which quiz to update")
        if not needs_id and not attrs.get("name"):
            raise ValueError(f"quizzes[{i}] is missing required attribute `name`")
        unknown = sorted(set(attrs) - permitted)
        if unknown:
            raise ValueError(
                f"quizzes[{i}] has unknown attribute(s) {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(permitted))}")
        if "name" in attrs and len(str(attrs["name"])) > 500:
            raise ValueError(f"quizzes[{i}] name must be at most 500 characters")
        pct = attrs.get("passing_percentage_correct")
        if pct is not None and not 0 <= int(pct) <= 100:
            raise ValueError(
                f"quizzes[{i}] passing_percentage_correct must be between 0 and 100")
        limit = attrs.get("time_limit_seconds")
        if limit is not None and not 0 <= int(limit) <= 3600000:
            raise ValueError(
                f"quizzes[{i}] time_limit_seconds must be between 0 and 3600000")
        align = attrs.get("alignment")
        if align is not None and align not in ALIGNMENTS:
            raise ValueError(
                f"quizzes[{i}] alignment {align!r} is invalid. One of: "
                f"{', '.join(ALIGNMENTS)}")


def _summary(row: dict[str, Any]) -> QuizOut:
    attrs = row.get("attributes", {})
    out: QuizOut = {"id": row.get("id", ""), "name": attrs.get("name", "")}
    for key in ("passing_percentage_correct", "max_attempts"):
        if key in attrs:
            out[key] = attrs[key]
    return out


def register_quiz_tools(app: MCPServer, get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_quizzes(filter_name: str | None = None, filter_updated_since: str | None = None,
                     page_cursor: str | None = None,
                     page_size: int | None = None) -> QuizListOut:
        """Find quizzes in this organization, by name or by when they last changed.

        Returns ONE PAGE. Check `has_more` - if it is true there are more quizzes than
        you can see, and you must call again with `next_cursor` before telling the user
        how many exist or that one is absent.

        `filter_name` is an EXACT match, case-insensitive - a partial name returns
        nothing. `filter_updated_since` needs an ISO-8601 timestamp WITH a timezone
        offset; a naive one is rejected.

        Returns settings only, not questions - use `list_questions` with `filter_quiz_id`
        for those. Requires the `quizzes:read` OAuth scope.
        """
        if page_size is not None and page_size < 1:
            raise ValueError("page_size must be 1 or greater")
        env = get_client().list_quizzes(name=filter_name, updated_since=filter_updated_since,
                                        cursor=page_cursor, page_size=page_size)
        out: QuizListOut = {"quizzes": [_summary(r) for r in env.get("data", [])],
                            "has_more": bool(env.get("has_more")), "note": _NOTE}
        nxt = env.get("next_cursor")
        if nxt:
            out["next_cursor"] = nxt
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_quiz(id: str) -> QuizDetailOut:
        """Fetch one quiz by its Skilljar id, with every setting.

        Returns scoring and presentation settings - passing percentage, attempt limit,
        time limit, randomisation - which `list_quizzes` does not. It does NOT return
        the quiz's questions; use `list_questions` with `filter_quiz_id` for those.

        Requires the `quizzes:read` OAuth scope.
        """
        row = get_client().get_quiz(quiz_id=id).get("data", {})
        attrs = row.get("attributes", {})
        out: QuizDetailOut = {"id": row.get("id", ""), "name": attrs.get("name", "")}
        for key in _DETAIL_KEYS:
            if key in attrs:
                out[key] = attrs[key]   # type: ignore[literal-required]
        return out

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_quizzes(quizzes: list[dict[str, Any]]) -> BatchResultOut:
        """Create one or more quizzes. This is a BATCH operation.

        `name` is required (max 500). Optional, with their defaults:
        `description_html` (""), `alignment` (center; left/center/right),
        `passing_percentage_correct` (0), `max_attempts` (0 = unlimited),
        `limit_question_count` (0 = use every question), `time_limit_seconds`
        (null = unlimited, max 3600000), and the booleans `randomize_questions`,
        `randomize_answers`, `require_correct_response`, `show_question_feedback`,
        `show_results_on_failure`, `skip_start_screen` (all false).

        A new quiz has NO questions - create them separately with `create_questions`
        and `quiz_id` set. Requires the `quizzes:write` OAuth scope.
        """
        _check_quiz_items(quizzes, needs_id=False)
        return _batch_out(get_client().create_quizzes(items=quizzes))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_quizzes(quizzes: list[dict[str, Any]]) -> BatchResultOut:
        """Update one or more existing quizzes. This is a BATCH operation.

        Each item needs an `id`. This is a PARTIAL update: an attribute you omit is
        PRESERVED, not cleared. Passing `description_html: ""` DOES clear it.

        Questions are not editable here - use `update_questions`. Requires the
        `quizzes:write` OAuth scope.
        """
        _check_quiz_items(quizzes, needs_id=True)
        return _batch_out(get_client().update_quizzes(items=quizzes))

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def delete_quizzes(quiz_ids: list[str]) -> BatchResultOut:
        """Delete one or more quizzes. DESTRUCTIVE. This is a BATCH operation.

        Pass `quiz_ids`, a list of obfuscated Skilljar quiz ids - a list even for one.

        What goes with the quiz, and what does NOT:

          deleted   the quiz, the questions it OWNS, and those questions' answers
          removed   its question-bank assignments (the links, not the banks)
          UNTOUCHED shared question banks and every question that lives in one

        A quiz only owns a question if that question was created with `quiz_id` set. A
        question created in a bank and used by this quiz SURVIVES - deleting the quiz
        does not destroy shared exam content.

        Requires the `quizzes:write` OAuth scope AND the `content.delete` capability,
        which is deliberately separate from `content.write` and is off in every profile
        except `full`. Take this action only on the user's explicit instruction.
        """
        if not quiz_ids:
            raise ValueError("quiz_ids must contain at least one id")
        return _batch_out(get_client().delete_quizzes(quiz_ids=quiz_ids))
