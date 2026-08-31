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
