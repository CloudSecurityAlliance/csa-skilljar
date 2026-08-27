"""Question banks and the quiz-to-bank binding.

The highest-value tools in the project: a bank is a reusable pool of exam items, and
the binding is what makes it reusable across quizzes. v1 can do neither - it cannot add
a question to a bank, and its quiz-to-bank endpoint is read-only.

The binding semantics are unusual and come from the captured official registry.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import (
    AssignmentListOut,
    AssignmentOut,
    BatchResultOut,
    QuestionBankListOut,
    QuestionBankOut,
)
from ._base import DESTRUCTIVE, READ, WRITE, translate_errors

_BANK_DETAIL_KEYS = ("question_count", "external_id", "created_at", "modified_at")
_ASSIGNMENT_FIELDS = frozenset({"question_bank_id", "order", "randomize_questions",
                                "limit_question_count"})

_NOTE = ("Results are one page. When has_more is true, call again with next_cursor. "
         "The official Skilljar MCP server cannot page at all; page_cursor and page_size "
         "are extensions here.")
_BATCH_NOTE = ("Rows are processed independently. A non-empty `failed` means some rows "
               "did not land - report that rather than reporting success.")
_ASSIGNMENT_NOTE = ("A quiz's bank assignments are a small bounded set, so this is not "
                    "paginated - every assignment is here.")


def _batch_out(envelope: dict[str, Any]) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]], "note": _BATCH_NOTE}


def _check_banks(items: list[dict[str, Any]], *, needs_id: bool) -> None:
    if not items:
        raise ValueError("question_banks must contain at least one item")
    permitted = {"name"} | ({"id"} if needs_id else set())
    for i, attrs in enumerate(items):
        if not isinstance(attrs, dict):
            raise ValueError(f"question_banks[{i}] must be an object of attributes")
        if needs_id and not attrs.get("id"):
            raise ValueError(f"question_banks[{i}] needs an `id`")
        if not needs_id and not attrs.get("name"):
            raise ValueError(f"question_banks[{i}] is missing required attribute `name`")
        unknown = sorted(set(attrs) - permitted)
        if unknown:
            raise ValueError(
                f"question_banks[{i}] has unknown attribute(s) {', '.join(unknown)}. "
                f"`name` is the only writable field. Allowed: {', '.join(sorted(permitted))}")
        if "name" in attrs and (not attrs["name"] or len(str(attrs["name"])) > 500):
            raise ValueError(
                f"question_banks[{i}] name must be non-empty and at most 500 characters")


def _check_assignments(items: list[dict[str, Any]], *, ids_only: bool = False) -> None:
    if not items:
        raise ValueError("question_banks must contain at least one item")
    permitted = {"question_bank_id"} if ids_only else _ASSIGNMENT_FIELDS
    for i, attrs in enumerate(items):
        if not isinstance(attrs, dict):
            raise ValueError(f"question_banks[{i}] must be an object")
        if not attrs.get("question_bank_id"):
            raise ValueError(f"question_banks[{i}] needs a `question_bank_id`")
        unknown = sorted(set(attrs) - permitted)
        if unknown:
            raise ValueError(
                f"question_banks[{i}] has unknown key(s) {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(permitted))}")
        for field in ("order", "limit_question_count"):
            v = attrs.get(field)
            if v is not None and not 0 <= int(v) <= 2147483647:
                raise ValueError(f"question_banks[{i}] {field} is out of range")


def _bank_summary(row: dict[str, Any]) -> QuestionBankOut:
    attrs = row.get("attributes", {})
    out: QuestionBankOut = {"id": row.get("id", ""), "name": attrs.get("name", "")}
    for key in _BANK_DETAIL_KEYS:
        if key in attrs:
            out[key] = attrs[key]   # type: ignore[literal-required]
    return out


def register_question_bank_tools(app: MCPServer,
                                 get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_question_banks(filter_name: str | None = None,
                            filter_updated_since: str | None = None,
                            page_cursor: str | None = None,
                            page_size: int | None = None) -> QuestionBankListOut:
        """Find reusable question banks in this organization, by name or last change.

        A question bank is a pool of exam items shared across quizzes, so the same
        certification questions can back several assessments without being duplicated.

        Returns ONE PAGE. Check `has_more` and call again with `next_cursor` before
        telling the user how many banks exist or that one is absent. `filter_name` is an
        EXACT match, case-insensitive.

        Does not return the banks' questions - use `list_questions` with
        `filter_question_bank_id`. Requires the `question-banks:read` OAuth scope.
        """
        if page_size is not None and page_size < 1:
            raise ValueError("page_size must be 1 or greater")
        env = get_client().list_question_banks(
            name=filter_name, updated_since=filter_updated_since,
            cursor=page_cursor, page_size=page_size)
        out: QuestionBankListOut = {
            "question_banks": [_bank_summary(r) for r in env.get("data", [])],
            "has_more": bool(env.get("has_more")), "note": _NOTE}
        nxt = env.get("next_cursor")
        if nxt:
            out["next_cursor"] = nxt
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_question_bank(id: str) -> QuestionBankOut:
        """Fetch one question bank by its Skilljar id.

        Returns the bank itself, not its questions - use `list_questions` with
        `filter_question_bank_id` for those, and `list_quiz_question_bank_assignments`
        to see which quizzes use it.

        Requires the `question-banks:read` OAuth scope.
        """
        return _bank_summary(get_client().get_question_bank(bank_id=id).get("data", {}))

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_question_banks(question_banks: list[dict[str, Any]]) -> BatchResultOut:
        """Create one or more question banks. This is a BATCH operation.

        Each item takes a single attribute, `name` (required, max 500). A new bank is
        EMPTY and bound to nothing: add items with `create_questions` and
        `question_bank_id` set, then attach it to a quiz with
        `bind_quiz_question_banks`.

        Requires the `question-banks:write` OAuth scope.
        """
        _check_banks(question_banks, needs_id=False)
        return _batch_out(get_client().create_question_banks(items=question_banks))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_question_banks(question_banks: list[dict[str, Any]]) -> BatchResultOut:
        """Rename one or more question banks. This is a BATCH operation.

        Pass `question_banks`, a list of items each needing an `id`. `name` is the ONLY writable field on a bank - its
        questions are managed with `create_questions` / `update_questions`, and its
        relationship to a quiz with the bind tools.

        Requires the `question-banks:write` OAuth scope.
        """
        _check_banks(question_banks, needs_id=True)
        return _batch_out(get_client().update_question_banks(items=question_banks))

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def delete_question_banks(question_bank_ids: list[str]) -> BatchResultOut:
        """Delete one or more question banks. DESTRUCTIVE. This is a BATCH operation.

        Pass `question_bank_ids`, a list of obfuscated Skilljar bank ids.

        What happens, and what does NOT:

          deleted    the bank, its questions, and those questions' answers
          removed    every assignment referencing it - so any quiz using this bank is
                     silently UNBOUND from it and loses those questions
          UNTOUCHED  the quizzes themselves, which stay alive

        A quiz that drew its items from this bank will still exist and still be
        deliverable, with fewer questions. Say so before doing it.

        Requires `question-banks:write` AND the `content.delete` capability, which is
        off in every profile except `full`. Take this action only on the user's explicit
        instruction.
        """
        if not question_bank_ids:
            raise ValueError("question_bank_ids must contain at least one id")
        return _batch_out(get_client().delete_question_banks(bank_ids=question_bank_ids))

    @app.tool(annotations=READ)
    @translate_errors
    def list_quiz_question_bank_assignments(quiz_id: str) -> AssignmentListOut:
        """Show which question banks a quiz draws from, and how it draws from each.

        Each assignment carries `order` (position within the quiz),
        `randomize_questions`, and `limit_question_count` (0 means use every question in
        the bank).

        Not paginated: a quiz's bank assignments are a small bounded set, so every one
        is returned. An unknown `quiz_id` is an error for the whole call.

        Requires the `quizzes:read` OAuth scope.
        """
        env = get_client().list_bank_assignments(quiz_id=quiz_id)
        rows: list[AssignmentOut] = []
        for row in env.get("data", []):
            attrs = row.get("attributes", {})
            item: AssignmentOut = {"question_bank_id": attrs.get("question_bank_id", "")}
            for key in ("order", "randomize_questions", "limit_question_count"):
                if key in attrs:
                    item[key] = attrs[key]
            rows.append(item)
        return {"quiz_id": quiz_id, "assignments": rows, "note": _ASSIGNMENT_NOTE}

    @app.tool(annotations=WRITE)
    @translate_errors
    def bind_quiz_question_banks(quiz_id: str,
                                 question_banks: list[dict[str, Any]]) -> BatchResultOut:
        """Attach question banks to a quiz, so it draws its items from them.

        Pass `quiz_id` and `question_banks`, a list of items each needing
        `question_bank_id`. Optional per item: `order` (omit and the bank is
        appended after the current last), `randomize_questions`, and
        `limit_question_count` (0 = use every question in the bank).

        RE-BINDING AN ALREADY-ATTACHED BANK IS A PARTIAL UPDATE, NOT A RESET. Only the
        fields you supply are written; anything you omit KEEPS ITS CURRENT VALUE, and an
        omitted `order` is NOT recalculated. So binding a bank that is already attached,
        with no other fields, changes nothing at all - it will not move the bank to the
        end and will not clear its settings.

        Within one call the FIRST occurrence of a bank wins; a later duplicate is
        reported as `duplicate_in_batch`. An unknown `quiz_id` fails the whole call; an
        unknown bank fails only its own row.

        Requires the `quizzes:write` OAuth scope.
        """
        _check_assignments(question_banks)
        return _batch_out(get_client().bind_banks(quiz_id=quiz_id, items=question_banks))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_quiz_question_banks(quiz_id: str,
                                   question_banks: list[dict[str, Any]]) -> BatchResultOut:
        """Change how a quiz draws from banks it is ALREADY attached to.

        Pass `quiz_id` and `question_banks`, a list of items each needing
        `question_bank_id` to say which assignment to change - it is the key, not a
        value you can edit. Then supply any of `order`,
        `randomize_questions`, `limit_question_count`.

        Supplying only the key is a successful no-op, not an error. A bank that is not
        currently attached to this quiz fails its own row with `not_found` - use
        `bind_quiz_question_banks` to attach it first.

        Requires the `quizzes:write` OAuth scope.
        """
        _check_assignments(question_banks)
        return _batch_out(
            get_client().update_bank_assignments(quiz_id=quiz_id, items=question_banks))

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def unbind_quiz_question_banks(quiz_id: str,
                                   question_banks: list[dict[str, Any]]) -> BatchResultOut:
        """Detach question banks from a quiz. The banks themselves are NOT deleted.

        Pass `quiz_id` and `question_banks`, a list of items each needing
        `question_bank_id`. Only the link is removed, permanently - the
        bank, its questions and every other quiz using it are untouched. The quiz keeps
        working with fewer questions.

        To delete the bank itself, use `delete_question_banks`. A bank not currently
        attached fails its own row with `not_found`.

        Requires the `quizzes:write` OAuth scope.
        """
        _check_assignments(question_banks, ids_only=True)
        return _batch_out(get_client().unbind_banks(quiz_id=quiz_id, items=question_banks))
