import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend, V2Backend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.web_packages import register_web_package_tools
from csa_skilljar.policy import Policy, PolicyBackend

PACKAGES = [
    {"type": "web-packages", "id": "wp1", "attributes": {
        "title": "Zero Trust SCORM", "display_name": "Zero Trust SCORM",
        "state": "READY", "type": "SCORM", "base_path": "/pkg/wp1/",
        "created_at": "2026-01-01T00:00:00Z", "modified_at": "2026-02-01T00:00:00Z"}},
    {"type": "web-packages", "id": "wp2", "attributes": {
        "title": "Draft Module", "display_name": "PROCESSING draft.zip",
        "state": "PROCESSING", "type": "SCORM", "base_path": ""}},
]


def build(profile="full"):
    fake = FakeBackend(web_packages=list(PACKAGES))
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_web_package_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, fake


@pytest.fixture
def tools():
    return build()[0]


# --- the asynchronous create ----------------------------------------------------------

def test_create_returns_processing_not_success(tools):
    """The trap: a model that reports "uploaded" here is reporting on a job that has not
    run. A bad archive surfaces as state ERROR later, never on this call."""
    out = tools["create_web_packages"](web_packages=[
        {"content_url": "https://example.org/pkg.zip", "title": "New"}])
    assert out["succeeded"] == 1
    assert "PROCESSING" in out["note"]
    assert "poll get_web_package" in out["note"]
    new_id = out["ids"][0]
    assert tools["get_web_package"](id=new_id)["state"] == "PROCESSING"


def test_create_description_says_success_is_not_completion(tools):
    doc = inspect.getdoc(tools["create_web_packages"]) or ""
    assert "SUCCESS HERE DOES NOT MEAN THE PACKAGE WORKS" in doc
    assert "ASYNCHRONOUS" in doc


def test_get_is_documented_as_the_polling_tool(tools):
    doc = inspect.getdoc(tools["get_web_package"]) or ""
    assert "THIS IS THE POLLING TOOL" in doc
    for state in ("PROCESSING", "READY", "ERROR"):
        assert state in doc


def test_there_is_no_dedup_on_content_url():
    """Every other create tool here dedups. This one must not: two identical URLs are a
    legitimate request for two distinct packages."""
    tools, fake = build()
    out = tools["create_web_packages"](web_packages=[
        {"content_url": "https://example.org/same.zip", "title": "One"},
        {"content_url": "https://example.org/same.zip", "title": "Two"}])
    assert out["succeeded"] == 2
    assert out["failed"] == []
    assert len(fake._web_packages) == 4


def test_content_url_must_be_https(tools):
    with pytest.raises(ToolError) as e:
        tools["create_web_packages"](web_packages=[
            {"content_url": "http://example.org/pkg.zip", "title": "New"}])
    assert "https://" in str(e.value)


def test_create_needs_a_title(tools):
    with pytest.raises(ToolError) as e:
        tools["create_web_packages"](web_packages=[
            {"content_url": "https://example.org/pkg.zip"}])
    assert "title" in str(e.value)


def test_title_length_is_bounded(tools):
    with pytest.raises(ToolError) as e:
        tools["create_web_packages"](web_packages=[
            {"content_url": "https://example.org/p.zip", "title": "x" * 501}])
    assert "500" in str(e.value)


# --- update: title only, and the display_name lag -------------------------------------

def test_update_rejects_the_silently_ignored_fields(tools):
    """Skilljar ACCEPTS these and ignores them - unusual for this API, which mostly
    forbids extras outright. ADR-008: refuse rather than let the caller believe it
    worked."""
    for field in ("type", "state", "base_path", "display_name"):
        with pytest.raises(ToolError) as e:
            tools["update_web_packages"](web_packages=[
                {"id": "wp1", "title": "Renamed", field: "anything"}])
        assert field in str(e.value)
        assert "silently ignores" in str(e.value)


def test_rename_of_a_processing_package_does_not_move_display_name():
    """The rename LOOKS like it did nothing: display_name lags until READY. A caller
    checking display_name concludes the write failed and retries forever."""
    tools, _ = build()
    tools["update_web_packages"](web_packages=[{"id": "wp2", "title": "Renamed"}])
    pkg = tools["get_web_package"](id="wp2")
    assert pkg["title"] == "Renamed"
    assert pkg["display_name"] == "PROCESSING draft.zip"


def test_rename_of_a_ready_package_moves_both():
    tools, _ = build()
    tools["update_web_packages"](web_packages=[{"id": "wp1", "title": "Renamed"}])
    pkg = tools["get_web_package"](id="wp1")
    assert pkg["title"] == pkg["display_name"] == "Renamed"


def test_update_description_warns_about_the_lag(tools):
    doc = inspect.getdoc(tools["update_web_packages"]) or ""
    assert "MAY LOOK LIKE IT DID NOTHING" in doc
    assert "ONLY WRITABLE FIELD" in doc


# --- delete: soft, and refused while in use -------------------------------------------

def test_delete_is_refused_while_a_live_lesson_uses_the_package():
    """A conflict, not a permission problem - and the message must say what to do about
    it, which means ConflictError has to survive translation."""
    tools, fake = build()
    fake.live_package_refs.add("wp1")
    with pytest.raises(ToolError) as e:
        tools["delete_web_package"](id="wp1")
    assert "live course" in str(e.value)
    assert "Unpublish the course or repoint the lesson" in str(e.value)


def test_delete_is_soft_and_delists():
    tools, fake = build()
    tools["delete_web_package"](id="wp1")
    assert [p["id"] for p in tools["list_web_packages"]()["web_packages"]] == ["wp2"]
    assert len(fake._web_packages) == 2          # nothing destroyed


def test_delete_takes_one_id_not_a_batch(tools):
    params = list(inspect.signature(tools["delete_web_package"]).parameters)
    assert params == ["id"]


# --- listing --------------------------------------------------------------------------

def test_listing_is_not_paginated(tools):
    out = tools["list_web_packages"]()
    assert "not paginated" in out["note"]
    assert "has_more" not in out
    assert list(inspect.signature(tools["list_web_packages"]).parameters) == []


def test_package_type_is_renamed_to_avoid_shadowing_json_api_type(tools):
    pkg = tools["get_web_package"](id="wp1")
    assert pkg["package_type"] == "SCORM"
    assert "type" not in pkg


# --- client registration --------------------------------------------------------------

def test_register_oauth_client_is_off_outside_the_admin_profile():
    for profile in ("parity", "authoring", "people", "operations"):
        tools, _ = build(profile=profile)
        with pytest.raises(ToolError) as e:
            tools["register_oauth_client"](client_name="x")
        assert "admin.credentials" in str(e.value)


def test_admin_profile_enables_it():
    tools, _ = build(profile="admin")
    out = tools["register_oauth_client"](client_name="my client")
    assert out["client_id"] == "fake-client-id"


def test_a_confidential_client_gets_a_one_time_secret_and_says_so():
    tools, _ = build(profile="admin")
    out = tools["register_oauth_client"](client_name="c")
    assert out["client_secret"] == "fake-one-time-secret"
    assert "ONCE and cannot be retrieved again" in out["warning"]


def test_a_public_client_gets_no_secret():
    tools, _ = build(profile="admin")
    out = tools["register_oauth_client"](
        client_name="c", token_endpoint_auth_method="none")
    assert out["client_secret"] is None


def test_auth_method_is_validated():
    tools, _ = build(profile="admin")
    with pytest.raises(ToolError) as e:
        tools["register_oauth_client"](client_name="c",
                                       token_endpoint_auth_method="magic")
    assert "client_secret_post" in str(e.value)


def test_description_says_a_dcr_client_is_not_an_org_credential():
    tools, _ = build(profile="admin")
    doc = inspect.getdoc(tools["register_oauth_client"]) or ""
    assert "NO ORGANIZATION IS BOUND" in doc
    assert "not a substitute" in doc.lower()
    assert "UNAUTHENTICATED" in doc


def test_registration_never_sends_our_bearer_token():
    """The security property. `_send` attaches Authorization to every call; routing
    registration through it would leak a live organization credential to an endpoint
    that neither wants nor needs it - and would fail outright when no credential is
    configured, which is the situation someone registering a client is in."""
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
                status_code = 201
                @staticmethod
                def json():
                    return {"client_id": "cid", "client_name": "c",
                            "redirect_uris": [], "grant_types": [],
                            "token_endpoint_auth_method": "none", "scope": ""}

            class Http:
                @staticmethod
                def post(url, json=None, headers=None):
                    captured["headers"] = headers
                    captured["url"] = url
                    return Resp()
            return Http()

    Spy().register_oauth_client(client_name="c")
    assert "Authorization" not in captured["headers"]
    assert captured["spec_path"] == "/v2/oauth/register"


def test_no_other_call_reaches_the_unauthenticated_path():
    """Enumerates the backend: `_register` must be used by registration alone. The
    failure mode is a later refactor routing something else through it and dropping that
    call's authentication."""
    import re
    from pathlib import Path
    source = Path("src/csa_skilljar/backend.py").read_text()
    callers = re.findall(r"return self\._register\(", source)
    assert len(callers) == 1, f"_register is called {len(callers)} times, expected 1"


def test_rfc7591_error_shape_is_surfaced_not_swallowed():
    """RFC 7591 errors are {error, error_description}, not JSON:API. `_receive` would
    report the status code and throw the description away."""
    from csa_skilljar import exceptions as exc

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
                status_code = 400
                @staticmethod
                def json():
                    return {"error": "invalid_redirect_uri",
                            "error_description": "redirect_uris must use https"}

            class Http:
                @staticmethod
                def post(url, json=None, headers=None):
                    return Resp()
            return Http()

    with pytest.raises(exc.ApiError) as e:
        Spy().register_oauth_client(client_name="c")
    assert "redirect_uris must use https" in str(e.value)
