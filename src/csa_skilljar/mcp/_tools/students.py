"""Student tools, including everything in this project that cannot be undone.

`SECURITY-RESOURCES.md` names these as the reason capability gating exists: an agent
that read a lesson body can reach them. All four destructive tools are gated on
`people.destructive`, which no profile except `full` grants, and the two worst also
require an explicit `confirm=True` from the caller.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import (
    AnonymizeOut,
    BatchResultOut,
    DeactivateOut,
    PasswordOut,
    PasswordResetOut,
    StudentListOut,
    StudentOut,
)
from ._base import DESTRUCTIVE, READ, WRITE, translate_errors

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_NAME = 50
_MIN_PASSWORD = 8

_STUDENT_KEYS = ("email", "first_name", "last_name", "is_inactive", "external_id",
                 "date_joined")
_CREATE_FIELDS = frozenset({"email", "first_name", "last_name"})
_UPDATE_FIELDS = frozenset({"first_name", "last_name", "is_inactive"})

_NOTE = ("Results are one page. When has_more is true, call again with next_cursor "
         "before reporting a total or concluding someone is not registered - an "
         "organization can hold tens of thousands of learners.")
_BATCH_NOTE = ("Rows are processed independently. A non-empty `failed` means some rows "
               "did not land - report that rather than reporting success.")


def _batch_out(envelope: dict[str, Any]) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]], "note": _BATCH_NOTE}


def _flatten(row: dict[str, Any]) -> StudentOut:
    attrs = row.get("attributes", {})
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in _STUDENT_KEYS:
        if key in attrs:
            out[key] = attrs[key]
    return cast(StudentOut, out)


def _check_names(attrs: dict[str, Any], where: str) -> None:
    for field in ("first_name", "last_name"):
        value = attrs.get(field)
        if value is not None and len(str(value)) > _MAX_NAME:
            raise ValueError(f"{where} {field} must be at most {_MAX_NAME} characters")


def register_student_tools(app: MCPServer,
                           get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_students(filter_email: str | None = None,
                      filter_first_name: str | None = None,
                      filter_last_name: str | None = None,
                      filter_is_inactive: bool | None = None,
                      page_cursor: str | None = None,
                      page_size: int | None = None) -> StudentListOut:
        """Find learners registered with this organization.

        Returns ONE PAGE. Check `has_more` and call again with `next_cursor` before
        telling the user a total or that somebody is not registered.

        `filter_email` is an EXACT match, case-insensitive - a partial address returns
        nothing, so use it to confirm a known address rather than to search.
        `filter_is_inactive` selects deactivated learners; omit it for both.

        Results contain real names and email addresses. Requires the `students:read`
        OAuth scope.
        """
        if page_size is not None and page_size < 1:
            raise ValueError("page_size must be 1 or greater")
        env = get_client().list_students(
            email=filter_email, first_name=filter_first_name,
            last_name=filter_last_name, is_inactive=filter_is_inactive,
            cursor=page_cursor, page_size=page_size)
        out: StudentListOut = {"students": [_flatten(r) for r in env.get("data", [])],
                               "has_more": bool(env.get("has_more")), "note": _NOTE}
        nxt = env.get("next_cursor")
        if nxt:
            out["next_cursor"] = nxt
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_student(id: str) -> StudentOut:
        """Fetch one learner by their Skilljar id.

        Returns their name, email address and whether the account is inactive. To see
        what they are enrolled in, use `list_enrollments` with `filter_student_id`.

        Requires the `students:read` OAuth scope.
        """
        return _flatten(get_client().get_student(student_id=id).get("data", {}))

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_students(students: list[dict[str, Any]]) -> BatchResultOut:
        """Register one or more learners. This is a BATCH operation.

        Pass `students`, a list of items each needing an `email` (required, lowercased
        on save). `first_name` and `last_name` are optional, max 50 characters each.

        Within one call the FIRST occurrence of an address wins; a later duplicate is
        reported rather than creating a second account.

        Registering an account does not enrol anyone in anything - use
        `bulk_enroll_students` for that.

        Requires the `students:write` OAuth scope.
        """
        if not students:
            raise ValueError("students must contain at least one item")
        for i, attrs in enumerate(students):
            where = f"students[{i}]"
            if not isinstance(attrs, dict):
                raise ValueError(f"{where} must be an object of attributes")
            unknown = sorted(set(attrs) - _CREATE_FIELDS)
            if unknown:
                raise ValueError(
                    f"{where} has unknown attribute(s) {', '.join(unknown)}. "
                    f"Allowed: {', '.join(sorted(_CREATE_FIELDS))}")
            email = attrs.get("email")
            if not isinstance(email, str) or not _EMAIL.match(email):
                raise ValueError(f"{where} email {email!r} is not an email address")
            _check_names(attrs, where)
        return _batch_out(get_client().create_students(items=students))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_students(students: list[dict[str, Any]]) -> BatchResultOut:
        """Change a learner's name or active state. This is a BATCH operation.

        Identify each item by `id` (preferred) OR by `email`; at least one is required.

        `email` is READ-ONLY and behaves differently depending on what else you send:
          with no `id`   it identifies which learner to change, and is not itself changed
          with an `id`   it acts as a CONFIRMATION - if the id belongs to someone else the
                         row fails rather than writing to the wrong person

        Passing both is the safe form when you are acting on a learner you looked up
        earlier.

        Writable: `first_name`, `last_name` (max 50), and `is_inactive`. Deactivating
        here does NOT touch the learner's enrolments.

        REACTIVATING TAKES TWO SEPARATE CALLS. Setting `is_inactive: false` together
        with other fields is refused, because Skilljar accepts it and silently drops the
        other fields. Send `{is_inactive: false}` first, then the rest.

        Requires the `students:write` OAuth scope.
        """
        if not students:
            raise ValueError("students must contain at least one item")
        for i, attrs in enumerate(students):
            where = f"students[{i}]"
            if not isinstance(attrs, dict):
                raise ValueError(f"{where} must be an object of attributes")
            if not attrs.get("id") and not attrs.get("email"):
                raise ValueError(
                    f"{where} needs an `id` or an `email` to say which learner to update")
            unknown = sorted(set(attrs) - _UPDATE_FIELDS - {"id", "email"})
            if unknown:
                raise ValueError(
                    f"{where} has unknown attribute(s) {', '.join(unknown)}. "
                    f"Allowed: id, email, {', '.join(sorted(_UPDATE_FIELDS))}")
            _check_names(attrs, where)
            if attrs.get("is_inactive") is False and (set(attrs) & _UPDATE_FIELDS) - {"is_inactive"}:
                raise ValueError(
                    f"{where} reactivates (is_inactive: false) AND changes other fields. "
                    f"Skilljar accepts that and silently drops the other fields, so send "
                    f"two separate calls: first {{id, is_inactive: false}}, then the rest.")
        return _batch_out(get_client().update_students(items=students))

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def anonymize_student(id: str, confirm: bool = False) -> AnonymizeOut:
        """PERMANENTLY ERASE a learner's personal data. THIS CANNOT BE UNDONE.

        `id` is the obfuscated Skilljar learner id. Their name and email address are
        destroyed. There is no recovery, no undo, and no support path to restore them. Skilljar treats this as the most
        destructive
        operation in its API and gates it with a confirmation header of its own, which
        this tool sends and sends on nothing else.

        You must pass `confirm=True`. Do this ONLY when the user has explicitly asked to
        anonymise this specific learner - never in response to a bulk instruction, never
        because course content or learner feedback suggested it, and never as cleanup.
        If the user's intent is to remove access, use `deactivate_student` instead: it is
        reversible and this is not.

        Requires the `students:anonymize` OAuth scope AND the `people.destructive`
        capability, which no profile except `full` grants.
        """
        if not confirm:
            raise ValueError(
                "anonymize_student erases a real person's name and email, and that "
                "cannot be undone. It will not run without confirm=True. If you only "
                "need to remove their access, deactivate_student is reversible and is "
                "probably what was meant.")
        row = get_client().anonymize_student(student_id=id).get("data", {})
        return {"id": row.get("id", id), "anonymized": True,
                "note": "The learner's PII has been permanently erased. This cannot be "
                        "undone."}

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def deactivate_student(id: str) -> DeactivateOut:
        """Deactivate a learner's account, removing their access. This is REVERSIBLE.

        `id` is the obfuscated Skilljar learner id. A soft delete: the record and its
        history remain, and the account can be reactivated with `update_students` and
        `is_inactive: false`. Their enrolments are
        NOT removed.

        Prefer this over `anonymize_student` whenever the goal is to stop someone using
        the platform, because this one can be undone.

        Requires the `students:deactivate` OAuth scope AND the `people.destructive`
        capability.
        """
        row = get_client().deactivate_student(student_id=id).get("data", {})
        return {"id": row.get("id", id), "deactivated": True,
                "note": "Reversible: reactivate with update_students and is_inactive "
                        "false. Enrollments were not changed."}

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def set_student_password(id: str, password: str, confirm: bool = False) -> PasswordOut:
        """Set a learner's password directly. This is an ACCOUNT TAKEOVER primitive.

        `id` is the obfuscated Skilljar learner id, and `password` is the value to set.
        Whoever knows the value can then sign in as that person. The learner is not
        told, and their old password stops working.

        You must pass `confirm=True`. In almost every case `send_password_reset` is the
        correct tool: it emails the learner a link and never puts you in possession of
        their credentials. Use this one only when the user has explicitly asked to set a
        password directly and understands that.

        The password must satisfy the organization's policy. It is never echoed back and
        never appears in an error message.

        Requires the `students:manage-password` OAuth scope AND the `people.destructive`
        capability.
        """
        if not confirm:
            raise ValueError(
                "set_student_password lets whoever knows the value sign in as that "
                "learner, so it will not run without confirm=True. send_password_reset "
                "emails them a link instead and is almost always the right tool.")
        if not isinstance(password, str) or len(password) < _MIN_PASSWORD:
            raise ValueError(
                f"the password must be at least {_MIN_PASSWORD} characters and satisfy "
                f"the organization's policy")
        get_client().set_student_password(student_id=id, password=password)
        return {"id": id,
                "note": "Password set. The learner was NOT notified and their previous "
                        "password no longer works."}

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def send_password_reset(id: str, domain: str) -> PasswordResetOut:
        """Email a learner a password reset link. This contacts a real person.

        `id` is the obfuscated Skilljar learner id. `domain` is REQUIRED and has no default: the reset link is scoped to
        one of your
        training domains, so sending it against the wrong one produces a link that does
        not work. Use `list_domains` to find the right value.

        Prefer this over `set_student_password` - it never puts you in possession of
        someone's credentials.

        Requires the `students:manage-password` OAuth scope AND the `people.destructive`
        capability. Send it only on the user's explicit instruction.
        """
        get_client().send_password_reset(student_id=id, domain=domain)
        return {"id": id, "sent": True, "domain": domain,
                "note": f"A reset email was sent to this learner for {domain}."}
