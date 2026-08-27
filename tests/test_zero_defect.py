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


# --- CodeQL py/clear-text-logging-sensitive-data: the standing counter-evidence -----

def test_no_credential_value_can_reach_the_cli_output(monkeypatch):
    """CodeQL reports `py/clear-text-logging-sensitive-data` on the startup warning.

    It is a false positive, and this test is the evidence that keeps it one. `os.environ`
    is a taint source and CodeQL does not distinguish "a value read from env" from "a
    module constant selected because of env" - three structural rewrites did not shift
    it. The dismissal on the alert points here.

    If this test ever fails, the dismissal is wrong and the alert should be reopened.
    """
    import contextlib
    import io

    from csa_skilljar.mcp import cli

    monkeypatch.setattr(cli, "_run_server", lambda *a, **k: None)
    secrets = {
        "CSA_SKILLJAR_V2_CLIENT_ID": "cid-SUPERSECRET-1",
        "CSA_SKILLJAR_V2_CLIENT_SECRET": "sk-live-SUPERSECRET-2",
        "CSA_SKILLJAR_V1_API_KEY": "v1key-SUPERSECRET-3",
    }
    for env in (secrets, {}, {k: v for k, v in secrets.items() if "V2" in k}):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main([], env=env)
        combined = out.getvalue() + err.getvalue()
        assert out.getvalue() == "", "stdout is the JSON-RPC channel"
        for value in secrets.values():
            assert value not in combined, f"credential value leaked into output: {value}"


# --- counter-evidence for the bandit B105/B107 dismissals ----------------------------
# A dismissed finding needs something that fails if the dismissal was wrong. These are
# that. See the "Dismissed static-analysis findings" table in SECURITY-RESOURCES.md.

def test_every_nosec_carries_a_reason():
    """A bare `# nosec` is an unreviewable suppression: it silences the scanner and
    records nothing about why. Requiring a rule id and a reason keeps each one
    auditable, and keeps the count small enough to read.

    The reason goes after a SECOND `#`. Bandit parses everything following the rule id
    as further rule ids, so `# nosec B105 - because ...` makes it warn once per word.
    """
    import pathlib
    import re
    src = pathlib.Path(__file__).resolve().parent.parent / "src"
    bare = []
    for path in src.rglob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if "nosec" not in line:
                continue
            # Expect: `# nosec B105 # <reason>`
            if not re.search(r"#\s*nosec\s+B\d{3}(?:,B\d{3})*\s+#\s*\S", line):
                bare.append(f"{path.name}:{n}")
    assert not bare, f"nosec without a rule id and reason: {bare}"


def test_the_dismissed_literals_are_what_they_claim_to_be():
    """The three B105/B107 hits are RFC 7591 vocabulary and one warning message, not
    credentials. If any of them is ever changed into something that IS a secret, this
    fails and the dismissal must be revisited."""
    from csa_skilljar.mcp._tools import web_packages as wp

    # RFC 7591 section 2: token_endpoint_auth_method values.
    assert wp._AUTH_METHODS == ("client_secret_post", "client_secret_basic", "none")
    # The warning is prose for a human, and must not contain anything secret-shaped.
    assert wp._SHOWN_ONCE_WARNING.startswith("If a client_secret is present")
    assert "=" not in wp._SHOWN_ONCE_WARNING


def test_a_registered_client_secret_is_never_logged_or_repeated(caplog):
    """The one place a real credential legitimately flows through this server. It must
    reach the caller and go nowhere else - not into a log record, not into a repr."""
    import logging

    from mcp.server import MCPServer

    from csa_skilljar.backend import FakeBackend
    from csa_skilljar.client import SkilljarClient
    from csa_skilljar.mcp._tools.web_packages import register_web_package_tools
    from csa_skilljar.policy import Policy, PolicyBackend

    client = SkilljarClient(PolicyBackend(FakeBackend(),
                                          Policy.from_profile("admin")))
    app = MCPServer(name="t")
    register_web_package_tools(app, lambda: client)
    tool = app._tool_manager._tools["register_oauth_client"].fn

    with caplog.at_level(logging.DEBUG):
        out = tool(client_name="c")

    secret = out["client_secret"]
    assert secret, "the fixture should return a secret, or this test proves nothing"
    for record in caplog.get_records("call"):
        assert secret not in record.getMessage()
    assert secret not in repr(client)
