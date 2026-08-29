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

# Tools that are ours, not Skilljar's, in TWO kinds - because they carry different
# risks and collapsing them would hide that.
#
# Server management touches no Skilljar API at all, so it cannot diverge from one.
SERVER_MANAGEMENT = {"check_access", "describe_capabilities", "report_a_problem"}

# Beyond-parity API tools DO call Skilljar, at endpoints the official server omits. They
# can drift with the vendor exactly like a parity tool can, and they are listed here so
# "extra" stays a deliberate register rather than a dumping ground.
BEYOND_PARITY = {
    # Block 10: Skilljar's server ships the tool that MINTS a credential and withholds
    # every tool that audits or remediates one. These are that second half.
    "list_oauth_clients", "get_oauth_client", "create_oauth_client",
    "update_oauth_client", "deactivate_oauth_client", "rotate_oauth_client_secret",
    "list_oauth_scopes", "revoke_refresh_token",
}

# Served by Skilljar's v1 API, which the official server does not touch at all. Kept
# separate from BEYOND_PARITY because the risk differs: these drift with a DIFFERENT
# API, on a different auth scheme and a different envelope.
V1_ONLY = {"find_learner", "list_learner_progress", "get_learner_progress",
           # Block 12 - v2 has no assets endpoint at all.
           "list_assets", "get_asset",
           # Block 13 - v2 has no commerce surface at all.
           "list_promo_codes", "list_promo_code_pools", "list_offers",
           "list_training_credit_codes", "get_purchase",
           # Block 14 - v2 has no path or series surface at all.
           "list_paths", "get_path", "list_path_items",
           "list_published_paths", "list_course_series",
           "list_learner_path_enrollments"}

OURS = SERVER_MANAGEMENT | BEYOND_PARITY | V1_ONLY


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


def test_our_additions_are_registered_and_correctly_classified():
    assert OURS <= set(registered())
    # The two kinds must stay disjoint: a tool that is both "touches no API" and
    # "calls an endpoint the official server omits" is a contradiction, and would mean
    # one of the two lists has stopped meaning what it says.
    assert not (SERVER_MANAGEMENT & BEYOND_PARITY)
    assert not (V1_ONLY & (SERVER_MANAGEMENT | BEYOND_PARITY))


def test_v1_only_tools_exist_because_v2_lacks_the_capability():
    """ADR-002. A v1 tool is justified only by a capability v2 does not have, so each
    must be absent from the v2 backend - otherwise it is duplication, not coverage."""
    from csa_skilljar.backend import Backend
    v2 = {n for n in dir(Backend) if not n.startswith("_")}
    duplicated = sorted(V1_ONLY & v2)
    assert not duplicated, f"v1 tools duplicating a v2 capability: {duplicated}"


def test_beyond_parity_tools_are_all_admin_gated():
    """Everything past parity so far is credential administration. If a future block adds
    a beyond-parity tool that is NOT admin-gated, this fails and the decision gets made
    deliberately rather than by omission."""
    from csa_skilljar import policy as P
    not_admin = sorted(n for n in BEYOND_PARITY
                       if P._GATES.get(n) != "admin.credentials")
    assert not not_admin, f"beyond-parity tools outside the admin gate: {not_admin}"


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
