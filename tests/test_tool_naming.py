import re

from csa_skilljar.mcp._config import ClientProvider, settings_from_env
from csa_skilljar.mcp.server import create_server


def tools():
    s = settings_from_env({})
    return create_server(ClientProvider(s), settings=s)._tool_manager._tools


def test_no_tool_name_carries_a_version_marker():
    """ADR-004: when a capability moves from v1 to v2 we change one backend and the tool
    keeps its name. A version prefix would force a rename that breaks every saved prompt."""
    for name in tools():
        assert not re.match(r"^v[0-9]_", name), name
        assert "_v1_" not in name and "_v2_" not in name, name


def test_all_four_block_one_tools_are_registered():
    assert set(tools()) == {"check_access", "describe_capabilities",
                            "report_a_problem", "list_courses"}


def test_the_server_carries_instructions_naming_the_untrusted_content_risk():
    s = settings_from_env({})
    app = create_server(ClientProvider(s), settings=s)
    assert app.instructions is not None
    assert "UNTRUSTED DATA" in app.instructions
