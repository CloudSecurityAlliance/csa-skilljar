"""Parity with the official Skilljar MCP server is a passing test, not a claim.

ADR-006 promises that a caller sending exactly what the official server accepts gets
exactly what it returns. A README sentence cannot enforce that; this can.

The reference is `specs/official-mcp/tool-names.json`, captured from the live server on
2026-08-26 before the connection was given up (FRICTION-001). It is the only copy that
exists, which is why the assertion is against the artifact rather than the network - a
test that needs an interactive login is a test that does not run.
"""
import inspect
import json
import pathlib

import pytest

from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server

ROOT = pathlib.Path(__file__).resolve().parent.parent
OFFICIAL = set(json.loads((ROOT / "specs" / "official-mcp" / "tool-names.json").read_text()))

# Tools that are ours, not Skilljar's. Every one is server management: none of them
# touches the Skilljar API surface, so none of them can diverge from it. Listed
# explicitly so "extra" cannot quietly become a dumping ground.
OURS = {"check_access", "describe_capabilities", "report_a_problem"}


def registered():
    def unreachable():
        raise AssertionError("listing tools must not construct a client")
    server = create_server(unreachable, settings=settings_from_env({}))
    return server._tool_manager._tools


def test_the_official_registry_is_the_expected_size():
    """Guards the guard. If the artifact were emptied or replaced, every assertion
    below would pass vacuously."""
    assert len(OFFICIAL) == 73


def test_every_official_tool_exists_here():
    """The headline claim of the project. A missing name means a caller written against
    Skilljar's server breaks against ours."""
    missing = sorted(OFFICIAL - set(registered()))
    assert not missing, f"not at parity - {len(missing)} official tools absent: {missing}"


def test_nothing_extra_ships_without_being_declared():
    """Additions are fine - the project exists to add things - but each must be a
    deliberate entry here rather than an accident of registration."""
    extra = sorted(set(registered()) - OFFICIAL - OURS)
    assert not extra, f"undeclared tools beyond the official surface: {extra}"


def test_our_additions_are_all_server_management():
    assert OURS <= set(registered())


@pytest.mark.parametrize("name", sorted(OFFICIAL))
def test_no_official_tool_name_carries_a_version_marker(name):
    """ADR-004. A `v1_`/`v2_` prefix would force a rename when Skilljar migrates a
    capability, breaking every saved prompt that used the old name."""
    assert not name.startswith(("v1_", "v2_"))
    assert "_v1_" not in name and "_v2_" not in name


@pytest.mark.parametrize("name", sorted(OFFICIAL))
def test_every_official_tool_has_a_real_description(name):
    """Parity is not just the name. A tool that exists with an empty docstring is
    present to a registry check and useless to a model."""
    doc = inspect.getdoc(registered()[name].fn) or ""
    assert len(doc) > 200, f"{name}: description is {len(doc)} chars, too thin to use"
