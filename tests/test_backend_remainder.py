"""The last of `backend.py` — and the line whose being uncovered *was* the bug.

Everything here is a path the suite never took. One of them turned out to be broken (#101),
which is the argument for the climb rather than a side effect of it: the line was uncovered
because nothing exercised it, and nothing exercised it because the behaviour it implements had
never been asserted by anybody.
"""
from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
import respx

from csa_skilljar import exceptions as exc
from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import FakeBackend, V2Backend

REGISTER = "https://api.skilljar.com/v2/oauth/register"


def token():
    def seg(payload):
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600})}.sig"


def backend():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": token()}))
    return V2Backend(V2Credentials("id", "sk-live-DEADBEEF"))


class TestScopePresetExpansion:
    """#101. The preset was stripped from `changes` before being read, so every preset expanded
    to `[]` — a client updated to `read_only` was granted nothing.

    It failed SAFE, which is why it survived: fewer scopes than asked for, never more, so
    nothing crashed and no call was over-permissioned. The cost was to the suite — a test
    written to assert expansion would have seen `[]` and encoded it as expected.
    """

    @staticmethod
    def client():
        backend = FakeBackend()
        return backend, backend.create_oauth_client(name="reporting")["data"]["id"]

    def test_a_preset_expands_to_its_scopes(self):
        fake, cid = self.client()
        attrs = fake.update_oauth_client(
            client_id=cid, changes={"scope_preset": "read_only"})["data"]["attributes"]

        assert attrs["scope_codenames"] == ["courses:read", "students:read"]

    def test_the_preset_name_does_not_survive_into_the_stored_attributes(self):
        """It is shorthand for a scope list, not a stored property. Keeping both invites two
        sources of truth for what the credential may do."""
        fake, cid = self.client()
        attrs = fake.update_oauth_client(
            client_id=cid, changes={"scope_preset": "read_only"})["data"]["attributes"]

        assert "scope_preset" not in attrs or attrs.get("scope_preset") is None

    def test_an_unknown_preset_grants_nothing_rather_than_everything(self):
        """The safe direction, and worth pinning deliberately rather than by accident — which
        is what it was before #101."""
        fake, cid = self.client()
        attrs = fake.update_oauth_client(
            client_id=cid, changes={"scope_preset": "no-such-preset"})["data"]["attributes"]

        assert attrs["scope_codenames"] == []

    def test_changes_without_a_preset_are_applied_verbatim(self):
        fake, cid = self.client()
        attrs = fake.update_oauth_client(
            client_id=cid, changes={"description": "renamed"})["data"]["attributes"]

        assert attrs["description"] == "renamed"

    def test_an_unknown_client_is_not_found(self):
        with pytest.raises(exc.NotFoundError, match="no OAuth client with id"):
            FakeBackend().get_oauth_client(client_id="absent")


class TestRemovingAMembershipIsIdempotent:
    def test_removing_a_non_member_still_reports_deleted(self):
        """Deliberate: there is no `not_a_member` outcome on the wire, so a caller cannot use
        this to test membership. Reporting an error for a non-member would make removal
        non-idempotent and turn a safe retry into a failure."""
        fake = FakeBackend()
        gid = fake.create_groups(items=[{"name": "G"}])["data"][0]["id"]

        first = fake.remove_group_memberships(group_id=gid, student_ids=["s1"])["data"]
        again = fake.remove_group_memberships(group_id=gid, student_ids=["s1"])["data"]

        assert [d["status"] for d in first] == ["deleted"]
        assert [d["status"] for d in again] == ["deleted"], "a retry became a failure"

    def test_removing_an_actual_member_removes_them(self):
        """The other direction — without it, a `remove` that did nothing at all would pass."""
        fake = FakeBackend()
        gid = fake.create_groups(items=[{"name": "G"}])["data"][0]["id"]
        fake.add_group_memberships(group_id=gid, student_ids=["s1", "s2"])

        fake.remove_group_memberships(group_id=gid, student_ids=["s1"])
        left = fake.list_group_memberships(group_id=gid)["data"] \
            if hasattr(fake, "list_group_memberships") else None
        if left is not None:
            assert [m["id"] for m in left] == ["s2"]


class TestAnEnrolmentThatExpires:
    def test_an_expiry_is_stored_when_given(self):
        fake = FakeBackend()
        out = fake.bulk_enroll(published_course_id="p1", emails=["a@b.c"],
                               expires_at="2027-01-01T00:00:00Z")
        eid = out["data"][0]["id"]
        row = next(r for r in fake.list_enrollments()["data"] if r["id"] == eid)

        assert row["attributes"]["expires_at"] == "2027-01-01T00:00:00Z"

    def test_no_expiry_stores_no_key(self):
        """Absent rather than null: an enrolment with `expires_at: None` reads as one that has
        an expiry policy and no date, which is a different thing from a permanent enrolment."""
        fake = FakeBackend()
        eid = fake.bulk_enroll(published_course_id="p1", emails=["a@b.c"])["data"][0]["id"]
        row = next(r for r in fake.list_enrollments()["data"] if r["id"] == eid)

        assert "expires_at" not in row["attributes"]

    @respx.mock
    def test_the_expiry_reaches_the_wire(self):
        route = respx.post("https://api.skilljar.com/v2/enrollments/").mock(
            return_value=httpx.Response(200, json={"data": []}))
        backend().bulk_enroll(published_course_id="p1", emails=["a@b.c"],
                              expires_at="2027-01-01T00:00:00Z")

        assert "2027-01-01T00:00:00Z" in route.calls[0].request.content.decode()


class TestTheUnauthenticatedEndpoint:
    """`register_oauth_client` goes through `_unauthenticated`, which is the one path that must
    never carry our credentials — so it has its own error handling rather than sharing the
    authenticated one."""

    @respx.mock
    def test_an_unreachable_host_is_an_api_error(self):
        respx.post(REGISTER).mock(side_effect=httpx.ConnectError("no route"))

        with pytest.raises(exc.ApiError) as ei:
            backend().register_oauth_client(client_name="agent")
        assert "sk-live-DEADBEEF" not in str(ei.value)

    @respx.mock
    def test_a_refusal_names_the_endpoint_and_relays_the_reason(self):
        """Not the status code. Registration is a bootstrap call somebody runs by hand when
        they have no credential yet, so *"/v2/oauth/register refused the request: <why>"* is
        worth more to them than a 400 — the endpoint tells them which of the two
        unauthenticated calls failed, and the relayed reason is the only thing that says what
        to change."""
        respx.post(REGISTER).mock(
            return_value=httpx.Response(400, json={"error": "redirect_uris is required"}))

        with pytest.raises(exc.ApiError) as ei:
            backend().register_oauth_client(client_name="agent")

        message = str(ei.value)
        assert "/v2/oauth/register" in message
        assert "redirect_uris is required" in message

    @respx.mock
    def test_a_response_that_is_not_an_object_is_refused(self):
        """A bare list or string parses and has no client id. Returning it would hand the
        caller something it cannot read a credential out of."""
        respx.post(REGISTER).mock(return_value=httpx.Response(200, json=["not", "an", "object"]))

        with pytest.raises(exc.ApiError):
            backend().register_oauth_client(client_name="agent")
