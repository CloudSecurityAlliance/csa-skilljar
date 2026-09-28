"""An OAuth-client option that is silently dropped creates a credential weaker than asked for.

`create_oauth_client` and `register_oauth_client` build their request body one `if … is not
None` at a time. Every one of those arms was unexecuted, and they are not ordinary optional
arguments — they are **the narrowing**:

    ip_allowlist       where the credential may be used from
    scope_codenames    what it may do
    scope_preset       the named bundle standing in for that list
    grant_types        which flows it may run

A dropped argument here does not fail. Skilljar creates the client happily, with **no** IP
restriction and whatever scope the default gives, and hands back a working secret. The caller
asked for a narrow credential, got a broad one, and nothing anywhere says so — the operator
finds out during an audit, or does not.

So the assertions are on the **request body**, which is the only place the difference is
visible before the credential exists.
"""
from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
import respx

from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import V2Backend

CLIENTS = "https://api.skilljar.com/v2/clients/"
REGISTER = "https://api.skilljar.com/v2/oauth/register"


def token():
    def seg(payload):
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600})}.sig"


def backend():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": token()}))
    return V2Backend(V2Credentials("id", "sk-live-DEADBEEF"))


def sent(route) -> dict:
    return json.loads(route.calls[0].request.content)


class TestCreatingAClient:
    @respx.mock
    def test_every_narrowing_option_reaches_the_body(self):
        """All four at once, because the failure is one of them going missing while the others
        arrive — which looks like success and produces a credential nobody asked for."""
        route = respx.post(CLIENTS).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().create_oauth_client(
            name="reporting", description="read-only reporting",
            scope_codenames=["courses:read", "lessons:read"],
            scope_preset="readonly",
            ip_allowlist=["203.0.113.4/32"])

        body = sent(route)
        assert body["name"] == "reporting"
        assert body["description"] == "read-only reporting"
        assert body["scope_codenames"] == ["courses:read", "lessons:read"]
        assert body["scope_preset"] == "readonly"
        assert body["ip_allowlist"] == ["203.0.113.4/32"]

    @respx.mock
    def test_an_omitted_option_is_absent_rather_than_null(self):
        """`"ip_allowlist": null` is a different request from omitting the key, and an API is
        entitled to read the first as *clear the allowlist*. Only `name` is required, so a
        minimal call must send exactly that."""
        route = respx.post(CLIENTS).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().create_oauth_client(name="minimal")

        assert sent(route) == {"name": "minimal"}

    @respx.mock
    def test_an_empty_allowlist_is_still_sent(self):
        """`[]` is not `None`. An explicitly empty allowlist may mean *allow nothing* — a
        deliberate lockdown — and dropping it because it is falsy would turn the narrowest
        request into the broadest outcome."""
        route = respx.post(CLIENTS).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().create_oauth_client(name="locked", ip_allowlist=[])

        assert "ip_allowlist" in sent(route), "an empty allowlist was dropped as falsy"
        assert sent(route)["ip_allowlist"] == []

    @respx.mock
    def test_an_empty_scope_list_is_still_sent(self):
        route = respx.post(CLIENTS).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().create_oauth_client(name="noscope", scope_codenames=[])

        assert sent(route)["scope_codenames"] == []


class TestRegisteringAClient:
    """`register_oauth_client` is one of two calls that must NOT carry our credentials — it is
    how a client is obtained in the first place."""

    @respx.mock
    def test_the_optional_flow_arguments_reach_the_body(self):
        route = respx.post(REGISTER).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().register_oauth_client(
            client_name="agent", grant_types=["client_credentials"], scope="courses:read")

        body = sent(route)
        assert body["grant_types"] == ["client_credentials"]
        assert body["scope"] == "courses:read"

    @respx.mock
    def test_omitting_them_sends_neither_key(self):
        route = respx.post(REGISTER).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().register_oauth_client(client_name="agent")

        body = sent(route)
        assert "grant_types" not in body and "scope" not in body
        assert body["redirect_uris"] == [], "a required key must still be present"

    @respx.mock
    def test_it_carries_no_authorization_header(self):
        """The property that makes it *register*. Sending a bearer token to the endpoint that
        issues credentials is how a bootstrap call quietly becomes an authenticated one, and
        then stops working for the case it exists for."""
        route = respx.post(REGISTER).mock(return_value=httpx.Response(200, json={"data": {}}))
        backend().register_oauth_client(client_name="agent")

        assert "authorization" not in {k.lower() for k in route.calls[0].request.headers}


class TestTheTransportFailing:
    @respx.mock
    def test_an_unreachable_skilljar_is_an_api_error_not_a_credential_error(self):
        """A network failure says nothing about the credential. Reporting it as a credential
        problem sends somebody to rotate a secret that was fine — the same distinction
        `test_auth.py` pins for the token grant, here for an ordinary call."""
        from csa_skilljar import exceptions as exc

        respx.post(CLIENTS).mock(side_effect=httpx.ConnectError("no route to host"))

        with pytest.raises(exc.ApiError) as ei:
            backend().create_oauth_client(name="x")

        assert "sk-live-DEADBEEF" not in str(ei.value)
