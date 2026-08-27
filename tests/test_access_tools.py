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
