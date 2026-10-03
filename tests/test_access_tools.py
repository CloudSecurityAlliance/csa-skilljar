from mcp.server import MCPServer

import csa_skilljar
from csa_skilljar.mcp._config import ClientProvider, settings_from_env
from csa_skilljar.mcp._tools.access import register_access_tools


def build(env):
    s = settings_from_env(env)
    app = MCPServer(name="t")
    register_access_tools(app, ClientProvider(s), s)
    return app


def fn(app, name):
    return app._tool_manager._tools[name].fn


def test_check_access_answers_with_no_credentials_at_all():
    out = fn(build({}), "check_access")()
    assert out["v2"]["configured"] is False
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in out["v2"]["detail"]
    assert out["version"] == csa_skilljar.__version__


def test_check_access_reports_the_active_profile():
    assert fn(build({"CSA_SKILLJAR_PROFILE": "authoring"}), "check_access")()["profile"] == "authoring"


def test_check_access_makes_no_network_call_when_v2_is_unconfigured(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("must not touch the network")

    monkeypatch.setattr(httpx.Client, "post", boom)
    fn(build({}), "check_access")()


def test_describe_capabilities_separates_enabled_from_available():
    out = fn(build({"CSA_SKILLJAR_PROFILE": "parity"}), "describe_capabilities")()
    assert "content.read" in out["enabled"]
    assert "people.destructive" in out["available_but_disabled"]
    assert "CSA_SKILLJAR_PROFILE" in out["how_to_change"]


def test_both_tools_are_registered_read_only():
    app = build({})
    for name in ("check_access", "describe_capabilities"):
        assert app._tool_manager._tools[name].annotations.read_only_hint is True


# ── Credential guidance ───────────────────────────────────────────────────────
#
# check_access is where everything else points a user whose credential failed, so what
# it says about obtaining one is the product, not a comment. Two of these are regression
# tests for a claim that was wrong for seven blocks: it said v1 had no tools while 27
# were registered, and `_require_v1` was actively routing users to read it.

def _v1_detail(configured: bool = False) -> str:
    from csa_skilljar.mcp._tools.access import v1_credential_detail
    return v1_credential_detail(configured)


def _v2_detail(configured: bool = False) -> str:
    from csa_skilljar.mcp._tools.access import v2_credential_detail
    return v2_credential_detail(configured)


def test_the_v1_guidance_is_consistent_with_the_registry():
    """The drift guard. If any registered tool needs the v1 key, the guidance must not
    say v1 tools are unimplemented - which is exactly what it said while 27 of them
    were shipping. Derived from the registry, so a future block cannot re-break it."""
    from csa_skilljar.mcp._config import Settings
    from csa_skilljar.mcp.server import create_server

    app = create_server(lambda: None, settings=Settings())
    tools = app._tool_manager._tools
    needs_v1 = [n for n, t in tools.items()
                if "CSA_SKILLJAR_V1_API_KEY" in (t.description or "")]
    assert needs_v1, "expected v1-backed tools to exist; update this guard if v1 is dropped"

    detail = _v1_detail(configured=False).lower()
    for lie in ("no v1-backed tools", "not currently needed", "no v1 tools yet"):
        assert lie not in detail, (
            f"{len(needs_v1)} tools require the v1 key, but the guidance says {lie!r}")


def test_the_v1_guidance_says_where_to_get_one():
    d = _v1_detail(configured=False)
    assert "dashboard.skilljar.com" in d
    assert "separate credential" in d.lower()      # neither substitutes for the other


def test_the_v2_guidance_says_where_to_get_one_and_warns_about_scopes():
    """Scopes are the part people actually get wrong: the first live demo run predicted
    zero refusals and hit two, because the profile allowed the calls and the token did
    not carry the scope. A missing scope needs the client re-issued, not a restart."""
    d = _v2_detail(configured=False)
    assert "dashboard.skilljar.com" in d
    assert "scope" in d.lower()


def test_the_guidance_says_there_is_no_interactive_login():
    """FRICTION-004. Absence of a login is indistinguishable from a missing feature, and
    the neighbouring CSA server does have one."""
    d = _v2_detail(configured=False).lower()
    assert "client_credentials" in d or "no browser" in d


def test_configured_details_stay_short():
    assert "dashboard" not in _v1_detail(configured=True).lower()
    assert "dashboard" not in _v2_detail(configured=True).lower()


# --- check_access when v2 IS configured -------------------------------------------
#
# The server's own instructions say: "IF A TOOL REPORTS A CREDENTIAL PROBLEM: call
# check_access." So this is the tool somebody reaches for when something is already wrong,
# and its whole body — everything that asks the credential about itself — had never run.
#
# It is driven through a stub credential rather than respx, because what is under test is
# how check_access REPORTS what the credential says, not how the credential learns it.
# `test_auth.py` owns the second question.

V2_ENV = {"CSA_SKILLJAR_V2_CLIENT_ID": "id", "CSA_SKILLJAR_V2_CLIENT_SECRET": "sk-live-X"}


class StubCredentials:
    def __init__(self, scopes, remaining=None, raises=None):
        self._scopes, self._remaining, self._raises = scopes, remaining, raises

    def granted_scopes(self):
        if self._raises is not None:
            raise self._raises
        return self._scopes

    def expires_in(self):
        return self._remaining


def with_credentials(credentials, env=None):
    """A server whose client hands back `credentials`, with v2 configured."""
    from csa_skilljar.mcp._config import settings_from_env

    settings = settings_from_env({**V2_ENV, **(env or {})})
    app = MCPServer(name="t")
    client = type("Client", (), {"credentials": credentials})()
    register_access_tools(app, lambda: client, settings)
    return app


def test_granted_scopes_are_listed_when_the_token_declares_them():
    out = fn(with_credentials(StubCredentials(["courses:read", "lessons:read"])),
             "check_access")()

    assert out["granted_scopes"] == ["courses:read", "lessons:read"]
    assert out["v2"]["working"] is True
    assert "scopes_unknown" not in out


def test_a_token_that_declares_nothing_is_unknown_rather_than_empty():
    """The three-state discipline. `None` from `granted_scopes()` means *the token did not
    say*, and an empty list means *it said none* — opposite facts with opposite remedies.
    Reporting the first as the second tells an operator their client was issued no scopes,
    which sends them to re-issue a credential that is working."""
    out = fn(with_credentials(StubCredentials(None)), "check_access")()

    assert out["scopes_unknown"] is True
    assert out["granted_scopes"] == [], "the list stays empty; the flag carries the meaning"
    assert out["v2"]["working"] is True, "unknown scopes is not a broken credential"


def test_a_token_that_genuinely_declares_none_is_not_flagged_unknown():
    """The other half, and the one that makes the flag mean something. Without this the
    assertion above passes against a server that always sets `scopes_unknown`."""
    out = fn(with_credentials(StubCredentials([])), "check_access")()

    assert out["granted_scopes"] == []
    assert "scopes_unknown" not in out


def test_the_remaining_lifetime_is_reported_when_it_is_known():
    out = fn(with_credentials(StubCredentials(["courses:read"], remaining=1800)),
             "check_access")()
    assert out["expires_in_seconds"] == 1800


def test_an_unknown_lifetime_is_absent_rather_than_zero():
    """Absent, not `0`. Zero reads as *expired now*, which would send somebody to re-issue a
    credential that has not expired and may never have said when it would."""
    out = fn(with_credentials(StubCredentials(["courses:read"], remaining=None)),
             "check_access")()
    assert "expires_in_seconds" not in out


def test_a_credential_that_cannot_answer_is_reported_not_raised():
    """The diagnostic must not itself fail. This is the tool somebody calls BECAUSE something
    is already broken — raising here replaces the diagnosis with a second traceback, and the
    caller learns nothing about the first problem."""
    from csa_skilljar import exceptions as exc

    out = fn(with_credentials(
        StubCredentials(None, raises=exc.CredentialsRejected("client was deleted"))),
        "check_access")()

    assert out["v2"]["working"] is False
    assert "client was deleted" in out["v2"]["detail"]
    assert out["version"], "the rest of the report still arrives"


def test_a_configured_but_absent_credential_does_not_claim_to_be_working():
    """`get_client().credentials` is None when v2 is configured and no credential was built.
    `working` must stay unset rather than being asserted on the strength of configuration —
    configured and working are different claims, which is the whole point of this tool."""
    out = fn(with_credentials(None), "check_access")()

    assert out["v2"]["configured"] is True
    assert out["v2"].get("working") is not True

# --- an unreachable Skilljar is not a broken credential -------------------------------------
#
# `exc.ApiError` and `exc.CredentialsRejected` are both `SkilljarError`, and a single
# `except exc.SkilljarError` reported them identically as `working: False`. `auth.py` goes to
# real trouble to distinguish them - `CredentialsRejected` says "re-issue the client in the
# Skilljar Dashboard", `ApiError` deliberately does not - and that was discarded here.


def _raising_client(err):
    """A server whose `.credentials` access itself raises, modelling the token exchange."""
    from csa_skilljar.mcp._config import settings_from_env

    class Client:
        @property
        def credentials(self):
            raise err

    app = MCPServer(name="t")
    register_access_tools(app, lambda: Client(), settings_from_env(V2_ENV))
    return app


def test_an_unreachable_skilljar_leaves_working_unset():
    """NOT `False`. The credential is not the thing that broke, and `working` is NotRequired
    in the schema for exactly this. Saying `False` advises re-issuing an organisation-wide
    credential because the network dropped - for a `client_credentials` grant that is a new
    organisation identity, which is not a cheap mistake to be talked into."""
    from csa_skilljar import exceptions as exc

    out = fn(_raising_client(exc.ApiError("could not reach Skilljar to authenticate: timeout")),
             "check_access")()
    assert "working" not in out["v2"], f"an unreachable Skilljar was called a dead credential: {out['v2']}"
    assert "could not be checked" in out["v2"]["detail"]
    assert "ApiError" in out["v2"]["detail"], "the cause has to survive to the caller"
    assert out["v2"]["configured"] is True, "it is still configured; that part was never in doubt"


def test_a_rate_limit_is_not_a_broken_credential_either():
    from csa_skilljar import exceptions as exc

    out = fn(_raising_client(exc.ApiError("token grant failed with HTTP 429", status=429)),
             "check_access")()
    assert "working" not in out["v2"], out["v2"]


def test_skilljar_refusing_the_client_IS_reported_as_not_working():
    """The other side of the split: Skilljar answered and said no. `auth.py`'s own message
    already names the remedy, so it is passed through rather than rewritten."""
    from csa_skilljar import exceptions as exc

    out = fn(_raising_client(exc.CredentialsRejected(
        "Skilljar rejected the v2 client credentials. Re-issue the client in the Skilljar "
        "Dashboard and restart the server.")), "check_access")()
    assert out["v2"]["working"] is False
    assert "Re-issue the client" in out["v2"]["detail"]


def test_a_hanging_token_endpoint_times_out_rather_than_hanging_the_diagnostic():
    """This tool's contract is that it answers when everything else is failing, so it must not
    be able to hang on the same outage the caller is asking about. Bounded on a thread, because
    `signal.alarm` is POSIX-only and these servers run on Windows laptops too."""
    import time

    from csa_skilljar.mcp._config import settings_from_env
    from csa_skilljar.mcp._tools import access as access_mod

    class Client:
        @property
        def credentials(self):
            time.sleep(30)
            raise AssertionError("should have been abandoned")

    app = MCPServer(name="t")
    register_access_tools(app, lambda: Client(), settings_from_env(V2_ENV))

    original = access_mod._VERIFY_TIMEOUT
    access_mod._VERIFY_TIMEOUT = 0.05
    try:
        started = time.monotonic()
        out = fn(app, "check_access")()
        took = time.monotonic() - started
    finally:
        access_mod._VERIFY_TIMEOUT = original
    assert "working" not in out["v2"], out["v2"]
    assert "did not answer within" in out["v2"]["detail"]
    assert took < 5, f"the bound did not hold: {took:.1f}s"


def test_nothing_configured_still_makes_no_call_at_all():
    """The property the module docstring promises, unchanged: with nothing configured it
    answers instantly, because there is nothing to ask about."""
    import time

    class Client:
        @property
        def credentials(self):
            raise AssertionError("check_access must not probe when nothing is configured")

    from csa_skilljar.mcp._config import settings_from_env

    app = MCPServer(name="t")
    register_access_tools(app, lambda: Client(), settings_from_env({}))
    started = time.monotonic()
    out = fn(app, "check_access")()
    assert out["v2"]["configured"] is False
    assert time.monotonic() - started < 1


def test_check_access_is_annotated_as_reaching_skilljar():
    """It calls Skilljar whenever a credential is configured, so it is open-world - while
    `describe_capabilities` beside it genuinely is not, which is why it has its own annotation
    rather than the shared `LOCAL_READ` being widened. A hint that lies is worse than an absent
    one, in either direction."""
    app = build({})
    checked = app._tool_manager._tools["check_access"]
    described = app._tool_manager._tools["describe_capabilities"]
    assert checked.annotations.open_world_hint is True
    assert checked.annotations.read_only_hint is True
    assert described.annotations.open_world_hint is False, (
        "describe_capabilities really is local - widening the shared annotation would have "
        "made this lie in the other direction"
    )
