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
from .v1backend import V1Backend

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
# Groups sit between content and people: they are administered like content, but a
# group membership decides which courses a learner can see. Neither content.* nor
# people.* is the right gate, so they get their own.
READ_GROUPS = "groups.read"
WRITE_GROUPS = "groups.write"
# Split out for the same reason content.delete is: deleting a group is a HARD delete
# and its memberships and visibility overrides cascade at the database.
DELETE_GROUPS = "groups.delete"
# Publishing is the only family whose effects are visible to the anonymous public: it
# puts a course on a customer-facing domain and can open it to anonymous access. An
# authoring credential that can write lesson HTML must not also be able to ship it.
READ_PUBLISHING = "publishing.read"
WRITE_PUBLISHING = "publishing.write"
READ_WEB_PACKAGES = "webpackages.read"
# v1-only. A read of learner progress is no more sensitive than list_enrollments, which
# `parity` already grants - so it goes in the same profiles rather than a stricter one.
READ_PROGRESS = "progress.read"
WRITE_WEB_PACKAGES = "webpackages.write"
ADMIN_CREDENTIALS = "admin.credentials"

ALL_CAPABILITIES: tuple[str, ...] = (
    READ_CONTENT, READ_PEOPLE, READ_REPORTING, WRITE_CONTENT, DELETE_CONTENT,
    WRITE_PEOPLE, WRITE_ENROLMENT, DESTRUCTIVE_PEOPLE, ADMIN_CREDENTIALS,
    READ_GROUPS, WRITE_GROUPS, DELETE_GROUPS, READ_PUBLISHING, WRITE_PUBLISHING,
    READ_WEB_PACKAGES, WRITE_WEB_PACKAGES, READ_PROGRESS,
)

# Named profiles, because nobody composes a capability list correctly under time
# pressure and everybody can pick a word. `parity` is the default.
PROFILES: dict[str, tuple[str, ...]] = {
    "parity": (READ_CONTENT, READ_PEOPLE, READ_REPORTING, READ_GROUPS,
               READ_PUBLISHING, READ_WEB_PACKAGES, READ_PROGRESS),
    "authoring": (READ_CONTENT, WRITE_CONTENT, READ_WEB_PACKAGES,
                  WRITE_WEB_PACKAGES),
    "people": (READ_PEOPLE, WRITE_PEOPLE, READ_GROUPS, WRITE_GROUPS),
    "reporting": (READ_REPORTING, READ_CONTENT),
    "operations": (READ_CONTENT, READ_PEOPLE, READ_REPORTING, WRITE_ENROLMENT,
                   READ_GROUPS, READ_PUBLISHING, READ_WEB_PACKAGES, READ_PROGRESS),
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
    "list_question_banks": READ_CONTENT,
    "get_question_bank": READ_CONTENT,
    "create_question_banks": WRITE_CONTENT,
    "update_question_banks": WRITE_CONTENT,
    "delete_question_banks": DELETE_CONTENT,
    "list_bank_assignments": READ_CONTENT,
    "bind_banks": WRITE_CONTENT,
    "update_bank_assignments": WRITE_CONTENT,
    "unbind_banks": WRITE_CONTENT,
    "list_enrollments": READ_REPORTING,
    "get_enrollment": READ_REPORTING,
    "list_certificates": READ_REPORTING,
    "get_certificate": READ_REPORTING,
    "get_course_analytics": READ_REPORTING,
    "list_course_ratings": READ_REPORTING,
    "update_enrollments": WRITE_ENROLMENT,
    "complete_enrollments": WRITE_ENROLMENT,
    "bulk_enroll": WRITE_ENROLMENT,
    "list_students": READ_PEOPLE,
    "get_student": READ_PEOPLE,
    "create_students": WRITE_PEOPLE,
    "update_students": WRITE_PEOPLE,
    "anonymize_student": DESTRUCTIVE_PEOPLE,
    "deactivate_student": DESTRUCTIVE_PEOPLE,
    "set_student_password": DESTRUCTIVE_PEOPLE,
    "send_password_reset": DESTRUCTIVE_PEOPLE,
    "list_groups": READ_GROUPS,
    "get_group": READ_GROUPS,
    "create_groups": WRITE_GROUPS,
    "update_groups": WRITE_GROUPS,
    "delete_groups": DELETE_GROUPS,
    "add_group_memberships": WRITE_GROUPS,
    "remove_group_memberships": WRITE_GROUPS,
    "list_signup_field_values": READ_GROUPS,
    "get_signup_field_value": READ_GROUPS,
    "create_signup_field_values": WRITE_GROUPS,
    "update_signup_field_values": WRITE_GROUPS,
    "list_published_courses": READ_PUBLISHING,
    "get_published_course": READ_PUBLISHING,
    "publish_courses": WRITE_PUBLISHING,
    "update_published_courses": WRITE_PUBLISHING,
    "delete_published_course": WRITE_PUBLISHING,
    "unpublish_published_course": WRITE_PUBLISHING,
    "republish_published_course": WRITE_PUBLISHING,
    "list_domains": READ_PUBLISHING,
    "get_domain": READ_PUBLISHING,
    # Visibility overrides are gated by groups.*, not publishing.*: upstream hangs them
    # off /v2/groups/{id}/... and requires student-groups:write. Gating by the scope the
    # credential actually needs keeps the local gate and the remote one in agreement.
    "list_visibility_overrides": READ_GROUPS,
    "add_visibility_overrides": WRITE_GROUPS,
    "remove_visibility_overrides": WRITE_GROUPS,
    "list_web_packages": READ_WEB_PACKAGES,
    "get_web_package": READ_WEB_PACKAGES,
    "create_web_packages": WRITE_WEB_PACKAGES,
    "update_web_packages": WRITE_WEB_PACKAGES,
    "delete_web_package": WRITE_WEB_PACKAGES,
    # Mints a credential. The official server ships it enabled; here it needs the
    # `admin` profile named explicitly (ADR-005), and RACI puts credential issuance
    # outside what an AI decides on its own.
    "register_oauth_client": ADMIN_CREDENTIALS,
    # Block 10. Everything that audits, constrains, rotates or revokes a credential.
    # Same gate as register_oauth_client: a tool that can enumerate and rotate every
    # credential in an organization is not something to have on by default.
    "list_oauth_clients": ADMIN_CREDENTIALS,
    "get_oauth_client": ADMIN_CREDENTIALS,
    "create_oauth_client": ADMIN_CREDENTIALS,
    "update_oauth_client": ADMIN_CREDENTIALS,
    "deactivate_oauth_client": ADMIN_CREDENTIALS,
    "rotate_oauth_client_secret": ADMIN_CREDENTIALS,
    "list_oauth_scopes": ADMIN_CREDENTIALS,
    "revoke_refresh_token": ADMIN_CREDENTIALS,
    # Block 11 - served by V1Backend, not V2Backend. One gate table covers both, so a
    # capability cannot be gated in one backend and open in the other.
    "find_learner": READ_PROGRESS,
    "list_learner_progress": READ_PROGRESS,
    "get_learner_progress": READ_PROGRESS,
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
    """Wraps a backend and refuses anything the policy does not permit.

    Either backend: the v2 `Backend` protocol or the v1 one. `_GATES` is a single table
    covering both, deliberately - a capability gated in one API and open in the other
    would be a hole nobody could see by reading either backend alone.
    """

    def __init__(self, backend: Backend | V1Backend, policy: Policy) -> None:
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
