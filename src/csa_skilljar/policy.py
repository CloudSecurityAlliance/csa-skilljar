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

import functools
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
# grants this - enforced by test_no_default_profile_grants_a_delete, which is written by
# hand rather than derived from PROFILES, so the table cannot vouch for itself.
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
DELETE_PUBLISHING = "publishing.delete"
READ_WEB_PACKAGES = "webpackages.read"
# v1-only. A read of learner progress is no more sensitive than list_enrollments, which
# `parity` already grants - so it goes in the same profiles rather than a stricter one.
READ_PROGRESS = "progress.read"
# Commerce is money: prices, discounts, prepaid balances and a customer's transaction.
# Its own capability rather than content.read, so a content-reading credential does not
# also see what everything costs and who bought it.
READ_COMMERCE = "commerce.read"
# Webhook configuration carries SECRETS - a shared-secret header value, a token in the
# target URL query string, a Basic-auth password. Its own capability, so a
# content-reading credential does not also learn where events go and with what
# authentication.
READ_EVENTS = "events.read"
WRITE_WEB_PACKAGES = "webpackages.write"
DELETE_WEB_PACKAGES = "webpackages.delete"
ADMIN_CREDENTIALS = "admin.credentials"

ALL_CAPABILITIES: tuple[str, ...] = (
    READ_CONTENT, READ_PEOPLE, READ_REPORTING, WRITE_CONTENT, DELETE_CONTENT,
    WRITE_PEOPLE, WRITE_ENROLMENT, DESTRUCTIVE_PEOPLE, ADMIN_CREDENTIALS,
    READ_GROUPS, WRITE_GROUPS, DELETE_GROUPS, READ_PUBLISHING, WRITE_PUBLISHING,
    READ_WEB_PACKAGES, WRITE_WEB_PACKAGES, DELETE_WEB_PACKAGES, READ_PROGRESS,
    READ_COMMERCE, READ_EVENTS, DELETE_PUBLISHING,
)

# Named profiles, because nobody composes a capability list correctly under time
# pressure and everybody can pick a word. `parity` is the default.
PROFILES: dict[str, tuple[str, ...]] = {
    "parity": (READ_CONTENT, READ_PEOPLE, READ_REPORTING, READ_GROUPS,
               READ_PUBLISHING, READ_WEB_PACKAGES, READ_PROGRESS),
    "authoring": (READ_CONTENT, WRITE_CONTENT, READ_WEB_PACKAGES,
                  WRITE_WEB_PACKAGES),
    "people": (READ_PEOPLE, WRITE_PEOPLE, READ_GROUPS, WRITE_GROUPS),
    # Commerce reads are analytical, so they belong with reporting - and
    # NOT with `parity`, which mirrors a server that has no commerce at all.
    "reporting": (READ_REPORTING, READ_CONTENT, READ_COMMERCE),
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
    # Annotated DESTRUCTIVE and it is: unbinding discards the binding, which the
    # authoring credential must not be able to do (T9).
    "unbind_banks": DELETE_CONTENT,
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
    "delete_published_course": DELETE_PUBLISHING,
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
    "delete_web_package": DELETE_WEB_PACKAGES,
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
    # Block 12. `content.read`, not a stricter gate: list_lessons already returns
    # content_asset_id under that capability, so gating assets harder would leave a
    # caller able to see the reference and unable to resolve it.
    "list_assets": READ_CONTENT,
    "get_asset": READ_CONTENT,
    # Block 13 - read-only by design (ADR-007), not merely by the write freeze.
    "list_promo_codes": READ_COMMERCE,
    "list_promo_code_pools": READ_COMMERCE,
    "list_offers": READ_COMMERCE,
    "list_training_credit_codes": READ_COMMERCE,
    "get_purchase": READ_COMMERCE,
    # Block 14. A path is a course sequence - content, under the same gate as courses.
    "list_paths": READ_CONTENT,
    "get_path": READ_CONTENT,
    "list_path_items": READ_CONTENT,
    "list_published_paths": READ_CONTENT,
    "list_course_series": READ_CONTENT,
    # A learner's enrolments in paths is progress, not content.
    "list_learner_path_enrollments": READ_PROGRESS,
    # Block 15.
    "list_webhooks": READ_EVENTS,
    "get_webhook": READ_EVENTS,
    # Gated by the BACKEND method name; the tool is called
    # `preview_event_payload`, which is the compression of ten endpoints.
    "get_sample_event_payload": READ_EVENTS,
    # Block 16. Sessions and their schedule are content; who attended is people.
    "list_ilt_sessions": READ_CONTENT,
    "list_vilt_session_events": READ_CONTENT,
    # An instructor's email is a real person's contact detail, and a registration
    # carries a learner's name and email on every row.
    "list_ilt_instructors": READ_PEOPLE,
    "list_vilt_registrations": READ_PEOPLE,
    # Block 17 - the last v1 family. Taxonomy is content metadata.
    "list_labels": READ_CONTENT,
    "list_tags": READ_CONTENT,
    "list_course_labels": READ_CONTENT,
    # A group category organises student groups, so it belongs with groups.read - the
    # same capability that reads the groups it categorises.
    "list_group_categories": READ_GROUPS,
}


# ── Reach: does the call cause Skilljar to contact a human? ─────────────────────
#
# Orthogonal to _GATES, and that is the point. A capability answers "what authority does
# the caller hold"; this answers "does the effect leave our boundary". They cross-cut:
# `send_password_reset` is support work and `bulk_enroll` is routine operations, neither
# is administration, and both cause a real person to receive an email.
#
# BACKEND METHOD names, not MCP tool names - the seam sees the former, and they differ
# (`bulk_enroll` is exposed as the tool `bulk_enroll_students`).
#
# Two kinds, because reach is not always a property of the tool. Enumerated by hand: a
# method that emails somebody and is on neither list is the failure this exists to
# prevent, and both expectations are re-stated by hand in test_policy.py.

#: Contacts a person on every call. Nothing in the arguments can prevent it.
ALWAYS_CONTACTS: frozenset[str] = frozenset({
    "send_password_reset",      # a reset link, to that learner's inbox
    "set_student_password",     # notifies the account holder
    "bulk_enroll",              # Skilljar emails each enrolled learner
})

#: Contacts a person only when an argument asks for it. The upstream API models the
#: decision explicitly, so we honour that rather than refusing the whole method - marking
#: an enrolment complete is useful work, and the email is a separable choice.
CONTACTS_WHEN: dict[str, str] = {
    "complete_enrollments": "send_notifications",
}

#: Every method that can contact a person, by either route.
CONTACTS_PEOPLE: frozenset[str] = ALWAYS_CONTACTS | frozenset(CONTACTS_WHEN)


class Policy:
    """What this install may do: which capabilities it holds, and whether it may reach a person.

    Two independent questions. `capabilities` answers "what authority does the caller
    hold"; `may_contact_people` answers "may an effect of that authority leave the
    building". A profile is chosen for the work someone does; contacting learners is a
    consequence they should agree to separately, because `operations` reads as routine and
    can otherwise email hundreds of people.
    """

    def __init__(self, capabilities: frozenset[str],
                 *, may_contact_people: bool = False) -> None:
        self.capabilities = frozenset(capabilities)
        self.may_contact_people = may_contact_people

    def __repr__(self) -> str:
        return (f"Policy({sorted(self.capabilities)!r}, "
                f"may_contact_people={self.may_contact_people})")

    @classmethod
    def from_profile(cls, name: str, *, may_contact_people: bool = False) -> Policy:
        try:
            return cls(frozenset(PROFILES[name]),
                       may_contact_people=may_contact_people)
        except KeyError:
            raise ValueError(
                f"unknown profile {name!r}. Choose one of: {', '.join(sorted(PROFILES))}"
            ) from None

    def allows(self, capability: str | None) -> bool:
        return True if capability is None else capability in self.capabilities

    def allows_reach(self, name: str, kwargs: dict[str, Any] | None = None) -> bool:
        """Whether this call may run, given whether it contacts a person.

        Checked in addition to the capability, never instead of it. For a method whose
        upstream API makes the notification a parameter, only the call that asks for the
        notification is refused - so `complete_enrollments(send_notifications=False)`
        works on an install that may not email anyone, which is the useful half.
        """
        if self.may_contact_people:
            return True
        if name in ALWAYS_CONTACTS:
            return False
        flag = CONTACTS_WHEN.get(name)
        if flag is None:
            return True
        return not bool((kwargs or {}).get(flag))


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
        target = getattr(self._backend, name)
        if name not in CONTACTS_PEOPLE:
            return target
        # Checked here rather than in the tool layer so a library embedder gets the same
        # refusal an MCP client does - one enforcement point, both questions. Wrapped
        # because for `CONTACTS_WHEN` methods the answer depends on the arguments.
        policy = self._policy

        @functools.wraps(target)
        def _reach_checked(*args: Any, **kwargs: Any) -> Any:
            if policy.allows_reach(name, kwargs):
                return target(*args, **kwargs)
            flag = CONTACTS_WHEN.get(name)
            remedy = (f"Pass {flag}=false to do the rest of the work without it, or set "
                      f"CSA_SKILLJAR_ALLOW_CONTACTING_PEOPLE=true and restart."
                      if flag else
                      "Set CSA_SKILLJAR_ALLOW_CONTACTING_PEOPLE=true and restart if that "
                      "is intended.")
            raise exc.PolicyError(
                f"`{name}` causes Skilljar to send email to real people, and this install "
                f"has not enabled that. It is a separate switch from the profile on "
                f"purpose: `{capability}` says what you may administer, this says whether "
                f"the effect may leave the building. {remedy} The policy cannot be "
                f"changed from here.")
        return _reach_checked
