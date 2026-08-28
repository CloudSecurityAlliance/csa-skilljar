import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend, V2Backend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.credentials import register_credential_tools
from csa_skilljar.policy import Policy, PolicyBackend

CLIENTS = [
    {"type": "clients", "id": "cl1", "attributes": {
        "name": "Reporting export", "description": "nightly job",
        "client_id": "cid-cl1", "is_active": True,
        "scope_codenames": ["courses:read", "students:read"], "ip_allowlist": []}},
    {"type": "clients", "id": "cl2", "attributes": {
        "name": "Retired importer", "client_id": "cid-cl2", "is_active": False,
        "scope_codenames": [], "ip_allowlist": ["203.0.113.7"]}},
]


def build(profile="admin"):
    fake = FakeBackend(oauth_clients=list(CLIENTS))
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_credential_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, fake


@pytest.fixture
def tools():
    return build()[0]


# --- the gate ------------------------------------------------------------------------

@pytest.mark.parametrize("name,kwargs", [
    ("list_oauth_clients", {}),
    ("get_oauth_client", {"id": "cl1"}),
    ("list_oauth_scopes", {}),
    ("create_oauth_client", {"name": "x", "scope_preset": "read_only"}),
    ("update_oauth_client", {"id": "cl1", "name": "y"}),
    ("deactivate_oauth_client", {"id": "cl1"}),
    ("rotate_oauth_client_secret", {"id": "cl1"}),
    ("revoke_refresh_token", {"token": "t"}),
])
@pytest.mark.parametrize("profile", ["parity", "authoring", "people", "operations"])
def test_every_credential_tool_is_off_outside_admin(name, kwargs, profile):
    """Not even the READS. Enumerating an organization's credentials is itself the
    reconnaissance step, so `list_oauth_clients` is gated exactly as hard as rotate."""
    tools, _ = build(profile=profile)
    with pytest.raises(ToolError) as e:
        tools[name](**kwargs)
    assert "admin.credentials" in str(e.value)


# --- trap 1: two ways to create, one of which does not work --------------------------

def test_the_two_creation_paths_are_disambiguated(tools):
    """register_oauth_client (official, DCR) binds NO organization, so its client
    authenticates and reads nothing forever. create_oauth_client is org-bound. A model
    holding one description must be able to tell which it is looking at."""
    doc = inspect.getdoc(tools["create_oauth_client"]) or ""
    assert "NOT `register_oauth_client`" in doc
    assert "BOUND TO YOUR ORGANIZATION" in doc
    assert "reads nothing" in doc


def test_create_returns_a_one_time_secret_and_says_so(tools):
    out = tools["create_oauth_client"](name="New job", scope_preset="read_only")
    assert out["client_secret"]
    assert "ONCE" in out["warning"]
    assert "cannot be retrieved again" in out["warning"]


def test_a_listing_never_carries_a_secret():
    tools, _ = build()
    tools["create_oauth_client"](name="New job", scope_preset="read_only")
    for row in tools["list_oauth_clients"]()["clients"]:
        assert "client_secret" not in row
    assert "client_secret" not in tools["get_oauth_client"](id="cl1")


# --- trap 7: two ways to say the same thing ------------------------------------------

def test_scopes_and_preset_together_are_refused(tools):
    with pytest.raises(ToolError) as e:
        tools["create_oauth_client"](name="x", scope_codenames=["courses:read"],
                                     scope_preset="read_only")
    assert "not both" in str(e.value)


def test_a_client_with_no_scopes_at_all_is_refused(tools):
    """A scopeless client authenticates and can do nothing, which reads as a broken
    credential rather than an empty one - so the confusion is worth preventing here."""
    with pytest.raises(ToolError) as e:
        tools["create_oauth_client"](name="x")
    assert "can authenticate and do nothing" in str(e.value)


def test_a_preset_expands_to_its_scopes():
    tools, fake = build()
    out = tools["create_oauth_client"](name="Reader", scope_preset="read_only")
    stored = tools["get_oauth_client"](id=out["id"])
    assert stored["scope_codenames"] == ["courses:read", "students:read"]


# --- update ---------------------------------------------------------------------------

def test_update_replaces_scopes_rather_than_adding(tools):
    tools["update_oauth_client"](id="cl1", scope_codenames=["courses:read"])
    assert tools["get_oauth_client"](id="cl1")["scope_codenames"] == ["courses:read"]


def test_update_description_warns_that_narrowing_is_not_immediate(tools):
    doc = inspect.getdoc(tools["update_oauth_client"]) or ""
    assert "NEXT TOKEN" in doc
    assert "rotate the secret" in doc.lower()


def test_update_needs_something_to_change(tools):
    with pytest.raises(ToolError) as e:
        tools["update_oauth_client"](id="cl1")
    assert "nothing to change" in str(e.value)


# --- trap 4: deactivate is not delete -------------------------------------------------

def test_deactivate_is_not_described_as_deletion(tools):
    doc = inspect.getdoc(tools["deactivate_oauth_client"]) or ""
    assert "DEACTIVATION, NOT A DELETION" in doc
    assert "Do not report it as deleted" in doc


def test_deactivate_keeps_the_row():
    tools, fake = build()
    tools["deactivate_oauth_client"](id="cl1")
    assert tools["get_oauth_client"](id="cl1")["is_active"] is False
    assert len(tools["list_oauth_clients"]()["clients"]) == 2      # nothing removed


# --- trap 6: rotation breaks things now -----------------------------------------------

def test_rotate_warns_the_old_secret_dies_immediately(tools):
    doc = inspect.getdoc(tools["rotate_oauth_client_secret"]) or ""
    assert "OLD ONE STOPS WORKING IMMEDIATELY" in doc
    assert "EVERY SERVICE STILL USING THE OLD SECRET IS" in doc


def test_rotate_returns_a_new_one_time_secret(tools):
    out = tools["rotate_oauth_client_secret"](id="cl1")
    assert out["client_secret"].startswith("rotated-")
    assert "ONCE" in out["warning"]


# --- trap 2: revoke is not confirmation -----------------------------------------------

def test_revoke_says_success_is_not_evidence(tools):
    """RFC 7009 §2.2, verified live: the endpoint answers 200 for a token that never
    existed, so it cannot be used to test whether one is valid. A model that reports
    'revoked' for a typo has told the user their leak is contained when it is not."""
    out = tools["revoke_refresh_token"](token="probably-a-typo")
    assert out["requested"] is True
    assert "not confirmation" in out["note"]
    doc = inspect.getdoc(tools["revoke_refresh_token"]) or ""
    assert "SUCCESS HERE IS NOT EVIDENCE" in doc
    assert "RFC 7009" in doc


def test_revoke_reaches_the_backend_even_though_it_cannot_confirm():
    tools, fake = build()
    tools["revoke_refresh_token"](token="rt-abc")
    assert fake.revoked_tokens == ["rt-abc"]


def test_revoke_needs_a_token(tools):
    with pytest.raises(ToolError):
        tools["revoke_refresh_token"](token="")


# --- trap 3: revoke sends no credentials ---------------------------------------------

def test_revoke_never_sends_our_bearer_token():
    """The second unauthenticated call. Verified against live Skilljar: revoke answers
    200 with no Authorization header at all. Routing it through `_send` would put a live
    organization token into a request that neither wants nor needs one."""
    captured = {}

    class Spy(V2Backend):
        def __init__(self):
            pass

        def _check_scope(self, method, spec_path):
            captured["spec_path"] = spec_path

        @property
        def _base(self):
            return "https://api.example"

        @property
        def _http(self):
            class Resp:
                status_code = 200
                @staticmethod
                def json():
                    raise ValueError("revoke returns an empty body")

            class Http:
                @staticmethod
                def post(url, json=None, headers=None):
                    captured["headers"] = headers
                    captured["body"] = json
                    return Resp()
            return Http()

    Spy().revoke_refresh_token(token="rt-abc", token_type_hint="refresh_token")
    assert "Authorization" not in captured["headers"]
    assert captured["spec_path"] == "/v2/auth/revoke"
    assert captured["body"]["token"] == "rt-abc"


def test_an_empty_success_body_is_not_treated_as_an_error():
    """Revoke returns 200 with NO body. The unauthenticated sender previously demanded
    JSON, which would have made every successful revocation look like a failure."""
    class Spy(V2Backend):
        def __init__(self):
            pass

        def _check_scope(self, method, spec_path):
            pass

        @property
        def _base(self):
            return "https://api.example"

        @property
        def _http(self):
            class Resp:
                status_code = 200
                @staticmethod
                def json():
                    raise ValueError("empty")

            class Http:
                @staticmethod
                def post(url, json=None, headers=None):
                    return Resp()
            return Http()

    out = Spy().revoke_refresh_token(token="rt-abc")
    assert out["data"]["type"] == "acknowledgement"


def test_exactly_two_calls_use_the_unauthenticated_path():
    """Was 'exactly one' until revoke arrived. Enumerating the backend keeps a later
    refactor from routing an authenticated call through it and dropping its credentials
    - the count is the guard, so it must move deliberately, not drift."""
    import re
    from pathlib import Path
    source = Path("src/csa_skilljar/backend.py").read_text()
    callers = re.findall(r"return self\._unauthenticated\(\"([^\"]+)\"", source)
    assert sorted(callers) == ["/v2/auth/revoke", "/v2/oauth/register"], callers


# --- scope catalogue -------------------------------------------------------------------

def test_scope_catalogue_returns_scopes_and_presets(tools):
    out = tools["list_oauth_scopes"]()
    assert {s["codename"] for s in out["scopes"]} >= {"courses:read", "clients:write"}
    assert out["presets"]["read_only"] == ["courses:read", "students:read"]
    assert "not what any one client was granted" in out["note"]


def test_scope_catalogue_points_at_the_per_client_view(tools):
    assert "get_oauth_client" in tools["list_oauth_scopes"]()["note"]
