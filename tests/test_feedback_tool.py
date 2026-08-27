from mcp.server import MCPServer

import csa_skilljar
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp._tools.feedback import register_feedback_tools


def build(env):
    s = settings_from_env(env)
    app = MCPServer(name="t")
    register_feedback_tools(app, s)
    return app._tool_manager._tools["report_a_problem"].fn


def test_report_includes_version_platform_and_profile():
    out = build({"CSA_SKILLJAR_PROFILE": "authoring"})(what_happened="list_courses returned nothing")
    assert csa_skilljar.__version__ in out["report"]
    assert "authoring" in out["report"]
    assert "list_courses returned nothing" in out["report"]
    assert "github.com/CloudSecurityAlliance/csa-skilljar/issues" in out["where_to_file"]


def test_report_never_contains_a_credential():
    out = build({"CSA_SKILLJAR_V2_CLIENT_ID": "cid-abc",
                 "CSA_SKILLJAR_V2_CLIENT_SECRET": "sk-live-DEADBEEF"})(what_happened="x")
    assert "cid-abc" not in out["report"]
    assert "sk-live-DEADBEEF" not in out["report"]
    assert "set" in out["report"].lower(), "it should say a credential IS configured, without the value"
