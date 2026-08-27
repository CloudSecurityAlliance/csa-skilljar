import base64
import contextlib
import json
import logging
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
    """A token in the RFC 6749/9068 shape: `scope`, a space-delimited STRING."""
    return jwt_with(exp=exp, scope=scope)


def jwt_with(*, exp: float, **claims) -> str:
    """Build a token with arbitrary claims, so a test can use the vendor's real shape.

    The original helper could only produce `scope` as a string. That is the standard,
    and it is not what Skilljar issues - see test_real_skilljar_token_shape below. A
    fixture that can only express our own assumption cannot catch a mismatch with the
    vendor, and this one did not: every scoped call was refused against a correctly
    scoped production token, and the whole suite stayed green.
    """
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp, **claims})}.sig"


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


# --- the vendor's real token shape ---------------------------------------------------
# Observed 2026-08-27 from a live client_credentials grant against api.skilljar.com.
# Claim names and types only; no values from that token appear here.
#
#   scopes            LIST of strings   <- what Skilljar issues
#   scope             absent            <- what RFC 6749 / RFC 9068 specify
#   exp, iat, aud, iss, jti, client_id, organization_id

@contextlib.contextmanager
def _creds(token):
    """A credentials object whose token grant returns `token`."""
    with respx.mock:
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={"access_token": token}))
        yield auth.V2Credentials("id", SECRET)


def test_scopes_claim_is_read_when_it_is_a_list():
    """The regression. Skilljar spells it `scopes` and sends a JSON list; this code read
    `scope` and string-split it, so granted_scopes() was empty for every real token and
    every scoped call was refused with "your client was issued: (none)" - against a
    client that had been issued seventeen scopes."""
    with _creds(jwt_with(exp=time.time() + 3600,
                         scopes=["courses:read", "quizzes:write"])) as c:
        assert c.granted_scopes() == ("courses:read", "quizzes:write")


def test_the_standard_scope_string_is_still_read():
    """RFC 6749 shape. Skilljar may move to it; the fix must not trade one for the
    other."""
    with _creds(jwt_with(exp=time.time() + 3600,
                         scope="courses:read quizzes:write")) as c:
        assert c.granted_scopes() == ("courses:read", "quizzes:write")


def test_a_scoped_call_is_permitted_against_a_real_shaped_token():
    """End of the chain, and the thing the user actually experiences: with the vendor's
    claim shape, require_scope must NOT raise for a scope the client holds."""
    with _creds(jwt_with(exp=time.time() + 3600, scopes=["courses:read"])) as c:
        c.require_scope("courses:read")                   # must not raise
        with pytest.raises(exc.ScopeError):
            c.require_scope("students:write")


def test_no_scope_claim_at_all_is_unknown_not_empty(caplog):
    """() and None are different answers. () means "issued nothing" and is a reason to
    refuse; None means the token did not say, and refusing on it would send the operator
    to re-issue a credential that is fine (ZD-17: an absorbing state that quietly
    refuses everything)."""
    with _creds(jwt_with(exp=time.time() + 3600)) as c, \
            caplog.at_level(logging.WARNING):
        assert c.granted_scopes() is None
        assert "no recognised scope claim" in caplog.text
        c.require_scope("courses:read")                   # must not raise on a guess


def test_an_explicitly_empty_scope_list_still_refuses():
    """The other side of that distinction: a token that really does declare no scopes
    is a real answer, and must still be refused locally."""
    with _creds(jwt_with(exp=time.time() + 3600, scopes=[])) as c:
        assert c.granted_scopes() == ()
        with pytest.raises(exc.ScopeError) as e:
            c.require_scope("courses:read")
        assert "(none)" in str(e.value)
