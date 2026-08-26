"""Guards derived from CINO-Platform-Engineering ZERO-DEFECT.md.

Each test here exists because an earlier version of this code had the defect it
describes. They are grouped separately from the feature tests because they encode a
*standard*, not a behaviour - and the standard applies to code not yet written.
"""
import base64
import json
import time

import httpx
import pytest
import respx

from csa_skilljar import auth
from csa_skilljar import exceptions as exc
from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import V2Backend


def seg(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


# --- ZD-1 / ZD-17: a swallowed exception that creates an absorbing state -----------

@respx.mock
def test_an_undecodable_token_is_reported_not_silently_swallowed(caplog):
    """ZD-1 'no swallowed exceptions'. decode_claims returning {} was silent, and the
    caller could not tell 'this token has no claims' from 'this token is not a JWT'."""
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "not-a-jwt", "expires_in": 3600}))
    c = V2Credentials("id", "sk-live-DEADBEEF")
    with caplog.at_level("WARNING"):
        c.token()
    assert "could not be decoded" in caplog.text


@respx.mock
def test_an_undecodable_token_does_not_re_grant_on_every_call(capsys):
    """ZD-17 'silence is not health'. With no `exp` claim, _expired() was permanently
    True, so every single call re-granted a token: correct code, false premise, and
    nothing anywhere would ever notice. This is the rotate-nginx-logs shape."""
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "not-a-jwt", "expires_in": 3600}))
    c = V2Credentials("id", "sk-live-DEADBEEF")
    c.token(); c.token(); c.token()
    assert respx.calls.call_count == 1, "an undecodable token must still be cached, not re-granted"


@respx.mock
def test_a_token_with_no_exp_uses_the_servers_expires_in(capsys):
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": f"{seg({'alg': 'none'})}.{seg({'scope': 'courses:read'})}.sig",
            "expires_in": 3600}))
    c = V2Credentials("id", "sk-live-DEADBEEF")
    c.token()
    remaining = c.expires_in()
    assert remaining is not None and 3000 < remaining <= 3600


# --- ZD-2 / ZD-17: an unknown operation must not look like "no scope needed" -------

@respx.mock
def test_an_unknown_operation_is_a_loud_error_not_a_skipped_scope_check():
    """ZD-2 'generate errors aggressively'. scopes_for() returns () for both a genuine
    pre-auth endpoint AND a typo'd path. Conflating them silently disables the scope
    pre-check for the typo - a security control that fails open and says nothing."""
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600, 'scope': 'courses:read'})}.sig"}))
    b = V2Backend(V2Credentials("id", "sk-live-DEADBEEF"))
    with pytest.raises(exc.SkilljarError) as e:
        b._get("/v2/coursez/")
    assert "not a known" in str(e.value).lower() or "unknown" in str(e.value).lower()


# --- ZD-2: a technically-successful response that is the wrong shape ---------------

@respx.mock
def test_a_200_that_is_not_json_becomes_a_typed_error():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600, 'scope': 'courses:read'})}.sig"}))
    respx.get("https://api.skilljar.com/v2/courses/").mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(exc.ApiError):
        V2Backend(V2Credentials("id", "sk-live-DEADBEEF")).list_courses()


@respx.mock
def test_a_200_whose_json_is_not_an_envelope_becomes_a_typed_error():
    """ZD-2: 'responses that technically succeed but look wrong - error on all of it'."""
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600, 'scope': 'courses:read'})}.sig"}))
    respx.get("https://api.skilljar.com/v2/courses/").mock(
        return_value=httpx.Response(200, json=["not", "an", "envelope"]))
    with pytest.raises(exc.ApiError):
        V2Backend(V2Credentials("id", "sk-live-DEADBEEF")).list_courses()


# --- ZD-1: diagnostics must never reach stdout ------------------------------------

def test_decode_claims_never_writes_to_stdout(capsys, caplog):
    """The library reports through `logging`; the CLI is what routes that to stderr.
    Nothing may reach stdout - it is the JSON-RPC channel."""
    with caplog.at_level("WARNING"):
        auth.decode_claims("not-a-jwt")
    assert capsys.readouterr().out == ""
    assert "could not be decoded" in caplog.text
