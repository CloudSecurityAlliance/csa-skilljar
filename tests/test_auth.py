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


# --- what happens when the grant does not go well ---------------------------------
#
# These are the paths a real deployment meets on its worst day and the suite had never
# executed: Skilljar answering with an error status, with something that is not JSON, or
# with a body that parses and carries no token. Each has to fail in a way that tells an
# operator which of those it was, because the remedies are different — re-issue the client,
# check the base URL, or call Skilljar.

class TestAGrantThatDoesNotYieldAToken:
    @staticmethod
    def creds():
        return auth.V2Credentials("id", SECRET)

    @respx.mock
    def test_a_server_error_is_an_api_error_carrying_the_status(self):
        """Not `CredentialsRejected`. A 500 says nothing about the credential, and telling
        somebody to re-issue a working client sends them to rotate a secret that was fine."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(500, json={}))

        with pytest.raises(exc.ApiError) as ei:
            self.creds().token()

        assert "500" in str(ei.value)
        assert SECRET not in str(ei.value)

    @respx.mock
    def test_a_response_that_is_not_json_says_so(self):
        """An HTML error page from a proxy, or a captive portal. The body cannot be shown -
        it may be arbitrary - so the message names the SHAPE problem rather than quoting it."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, text="<html>Service Unavailable</html>"))

        with pytest.raises(exc.ApiError, match="not JSON"):
            self.creds().token()

    @respx.mock
    def test_json_that_is_not_an_object_is_refused(self):
        """A bare list or string parses cleanly and has no `access_token`. Reaching for
        `.get` on it raises `AttributeError` three frames away from the cause."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json=["not", "an", "object"]))

        with pytest.raises(exc.ApiError, match="not an object"):
            self.creds().token()

    @respx.mock
    def test_an_object_with_no_access_token_is_refused(self):
        """The shape Skilljar returns when the grant is understood and declined. Storing the
        `None` would make every later call fail with a bearer header reading `Bearer None`."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={"token_type": "Bearer"}))

        with pytest.raises(exc.ApiError, match="no access_token"):
            self.creds().token()

    @respx.mock
    def test_none_of_these_leak_the_secret(self):
        """The property `SECRET` exists for. Four different failure paths, one credential."""
        for response in (httpx.Response(500, json={}),
                         httpx.Response(200, text="<html/>"),
                         httpx.Response(200, json=[]),
                         httpx.Response(200, json={})):
            respx.post("https://api.skilljar.com/v2/auth/token").mock(return_value=response)
            with pytest.raises(exc.SkilljarError) as ei:
                auth.V2Credentials("id", SECRET).token()
            assert SECRET not in str(ei.value)


class TestTheExpiryIsAlwaysKnown:
    """`_expired()` returns True when `_expiry` is None, and the comment beside it records
    what that cost: it *was* always None, so every single call re-granted a token. Correct
    code on a false premise, and nothing would ever have reported it - the server worked, it
    simply authenticated on every request.

    So the invariant is that `_resolve_expiry` never returns None, from whichever of three
    sources it can reach.
    """

    @staticmethod
    def creds():
        return auth.V2Credentials("id", SECRET)

    @respx.mock
    def test_the_tokens_own_exp_is_preferred(self):
        """The JWT is the authority: it is what Skilljar will actually enforce, and the
        grant's `expires_in` is a duration measured from a clock we do not share."""
        expiry = time.time() + 1800
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": make_jwt(exp=expiry), "expires_in": 60}))

        credentials = self.creds()
        credentials.token()
        assert credentials._expiry == pytest.approx(expiry, abs=1)

    @respx.mock
    def test_expires_in_is_used_when_the_token_carries_no_exp(self):
        """An opaque token, or one this decoder could not read. The grant still said how long
        it lasts, and using it beats re-granting on every call."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": "opaque-not-a-jwt", "expires_in": 900}))

        credentials = self.creds()
        credentials.token()
        assert credentials._expiry == pytest.approx(time.time() + 900, abs=5)

    @respx.mock
    def test_neither_source_falls_back_to_a_short_window_and_says_so(self, caplog):
        """Last resort, and it warns - an unannounced fallback is how a wrong lifetime
        becomes a mystery. Short and conservative on purpose: guessing LONG means calls
        failing on an expired token, guessing short means re-granting sooner than needed."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "opaque-not-a-jwt"}))

        credentials = self.creds()
        with caplog.at_level(logging.WARNING, logger="csa_skilljar"):
            credentials.token()

        assert credentials._expiry is not None, "the cache is disabled whenever this is None"
        assert credentials._expiry > time.time()
        assert any("no expiry" in r.getMessage() for r in caplog.records)

    @respx.mock
    def test_a_zero_or_negative_expires_in_is_not_trusted(self):
        """`expires_in: 0` would set an expiry in the past, so every call re-grants - the
        exact defect the comment beside `_expired` records, arriving from the other side."""
        respx.post("https://api.skilljar.com/v2/auth/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": "opaque-not-a-jwt", "expires_in": 0}))

        credentials = self.creds()
        credentials.token()
        assert credentials._expiry > time.time()


def test_a_token_whose_payload_is_not_an_object_decodes_to_no_claims(caplog):
    """A JWT whose payload is a bare JSON array. It decodes, it is not a dict, and reaching
    for `.get("exp")` on it would raise inside the expiry path rather than at the token."""
    segment = base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode()).rstrip(b"=").decode()
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()

    with caplog.at_level(logging.WARNING, logger="csa_skilljar"):
        claims = auth.decode_claims(f"{header}.{segment}.sig")

    assert claims == {}
    assert any("not an object" in r.getMessage() for r in caplog.records)
