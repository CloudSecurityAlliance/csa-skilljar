import base64
import json
import time

import httpx
import pytest
import respx

from csa_skilljar import auth
from csa_skilljar import exceptions as exc

# A value that cannot collide with ordinary English prose in an error message. The plan
# originally asserted `"secret" not in str(e)`, which would forbid the *word* secret in a
# perfectly good remedy ("the secret may have been rotated"). The property under test is
# that the credential VALUE never leaks, so use a value nothing would say by accident.
SECRET = "sk-live-DEADBEEF-do-not-log"


def make_jwt(*, exp: float, scope: str = "courses:read lessons:read") -> str:
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp, 'scope': scope})}.sig"


def test_decode_claims_reads_exp_and_scope():
    claims = auth.decode_claims(make_jwt(exp=123.0))
    assert claims["exp"] == 123.0
    assert claims["scope"] == "courses:read lessons:read"


def test_decode_claims_on_garbage_returns_empty_not_raise():
    # A malformed token must not crash startup - Tier 1 runs before anything is verified.
    assert auth.decode_claims("not-a-jwt") == {}


@respx.mock
def test_token_grant_uses_client_credentials():
    route = respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": make_jwt(exp=time.time() + 3600),
                                               "token_type": "Bearer", "expires_in": 3600}))
    c = auth.V2Credentials("id", SECRET)
    assert c.token().count(".") == 2
    body = route.calls[0].request.content.decode()
    assert "grant_type=client_credentials" in body


@respx.mock
def test_token_is_cached_until_near_expiry():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": make_jwt(exp=time.time() + 3600)}))
    c = auth.V2Credentials("id", SECRET)
    c.token(); c.token(); c.token()
    assert respx.calls.call_count == 1, "token must be cached, not re-granted per call"


@respx.mock
def test_rejected_client_raises_credentials_rejected_without_echoing_the_secret():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"}))
    c = auth.V2Credentials("id", SECRET)
    with pytest.raises(exc.CredentialsRejected) as e:
        c.token()
    assert SECRET not in str(e.value)
    assert SECRET not in repr(c), "__repr__ is what embedders log"


@respx.mock
def test_granted_scopes_come_from_the_token():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": make_jwt(exp=time.time() + 3600, scope="courses:read quizzes:write")}))
    c = auth.V2Credentials("id", SECRET)
    assert c.granted_scopes() == ("courses:read", "quizzes:write")


@respx.mock
def test_require_scope_raises_locally_without_a_call():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={
            "access_token": make_jwt(exp=time.time() + 3600, scope="courses:read")}))
    c = auth.V2Credentials("id", SECRET)
    c.require_scope("courses:read")                      # present: no raise
    with pytest.raises(exc.ScopeError) as e:
        c.require_scope("question-banks:write")
    assert e.value.required == "question-banks:write"
    assert "courses:read" in e.value.granted


@respx.mock
def test_unreachable_skilljar_is_an_api_error_not_a_credential_error():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(exc.ApiError):
        auth.V2Credentials("id", SECRET).token()
