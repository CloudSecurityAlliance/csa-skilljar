"""Capability gating, enforced by a wrapper around the Backend seam.

Two properties are load-bearing and must survive any future rework (ADR-005):

* **One wrapper.** Enforcement lives here, not in the tools, so a library embedder
  gets the same guarantee as an MCP client.
* **Fail closed.** `_GATES` must name every `Backend` method. An unlisted name is
  REFUSED, not delegated - so a newly added capability arrives *off* rather than
  ungoverned, and forgetting a declaration turns a feature off instead of leaving
  a hole. `tests/test_policy.py` fails CI when the two drift.

The policy cannot be widened in-band: no tool changes it, and the configuration is
the complete permitted list rather than a delta.
"""
from __future__ import annotations

from typing import Any

from . import exceptions as exc
from .backend import Backend

READ_CONTENT = "content.read"
READ_PEOPLE = "people.read"
READ_REPORTING = "reporting.read"
WRITE_CONTENT = "content.write"
# Deletes are gated separately from writes on purpose: an authoring credential that can
# create and update content should not thereby be able to destroy it. No default profile
# grants this.
DELETE_CONTENT = "content.delete"
WRITE_PEOPLE = "people.write"
WRITE_ENROLMENT = "enrolment.write"
DESTRUCTIVE_PEOPLE = "people.destructive"
ADMIN_CREDENTIALS = "admin.credentials"

ALL_CAPABILITIES: tuple[str, ...] = (
    READ_CONTENT, READ_PEOPLE, READ_REPORTING, WRITE_CONTENT, DELETE_CONTENT,
    WRITE_PEOPLE, WRITE_ENROLMENT, DESTRUCTIVE_PEOPLE, ADMIN_CREDENTIALS,
)

# Named profiles, because nobody composes a capability list correctly under time
# pressure and everybody can pick a word. `parity` is the default.
PROFILES: dict[str, tuple[str, ...]] = {
    "parity": (READ_CONTENT, READ_PEOPLE, READ_REPORTING),
    "authoring": (READ_CONTENT, WRITE_CONTENT),
    "people": (READ_PEOPLE, WRITE_PEOPLE),
    "reporting": (READ_REPORTING, READ_CONTENT),
    "operations": (READ_CONTENT, READ_PEOPLE, READ_REPORTING, WRITE_ENROLMENT),
    "admin": (ADMIN_CREDENTIALS,),
    "full": ALL_CAPABILITIES,
}

# Every Backend method needs an entry. None means "no capability required" (a pure
# read the policy does not gate); a string names the capability that gates it.
_GATES: dict[str, str | None] = {
    "list_courses": READ_CONTENT,
    "get_course": READ_CONTENT,
    "list_lessons": READ_CONTENT,
    "get_lesson": READ_CONTENT,
    "create_courses": WRITE_CONTENT,
    "update_courses": WRITE_CONTENT,
    "create_lessons": WRITE_CONTENT,
    "update_lessons": WRITE_CONTENT,
    "list_quizzes": READ_CONTENT,
    "get_quiz": READ_CONTENT,
    "create_quizzes": WRITE_CONTENT,
    "update_quizzes": WRITE_CONTENT,
    "delete_quizzes": DELETE_CONTENT,
    "list_questions": READ_CONTENT,
    "get_question": READ_CONTENT,
    "create_questions": WRITE_CONTENT,
    "update_questions": WRITE_CONTENT,
    "delete_questions": DELETE_CONTENT,
}


class Policy:
    def __init__(self, capabilities: frozenset[str]) -> None:
        self.capabilities = frozenset(capabilities)

    def __repr__(self) -> str:
        return f"Policy({sorted(self.capabilities)!r})"

    @classmethod
    def from_profile(cls, name: str) -> Policy:
        try:
            return cls(frozenset(PROFILES[name]))
        except KeyError:
            raise ValueError(
                f"unknown profile {name!r}. Choose one of: {', '.join(sorted(PROFILES))}"
            ) from None

    def allows(self, capability: str | None) -> bool:
        return True if capability is None else capability in self.capabilities


class PolicyBackend:
    """Wraps a Backend and refuses anything the policy does not permit."""

    def __init__(self, backend: Backend, policy: Policy) -> None:
        self._backend = backend; self._policy = policy

    @property
    def policy(self) -> Policy:
        return self._policy

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in _GATES:
            raise exc.PolicyError(
                f"`{name}` has no declared capability gate, so it is refused. This is a "
                f"programming error in csa-skilljar, not a configuration problem: add an "
                f"entry to policy._GATES.")
        capability = _GATES[name]
        if not self._policy.allows(capability):
            raise exc.PolicyError(
                f"`{name}` needs the `{capability}` capability, which this install does not "
                f"enable. Set CSA_SKILLJAR_PROFILE to a profile that includes it, then "
                f"restart. The policy cannot be changed from here.")
        return getattr(self._backend, name)
