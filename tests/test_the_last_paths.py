"""The paths nothing else reaches: transport failures, reprs, and two config branches.

Not a theme, which is the point. Everything above this file is a census over a population;
these are what is left once the populations are exhausted, and they are exactly the lines
that stay uncovered for ever because no group of them is big enough to be worth a pattern.

Several are error paths on the v1 transport. Those matter more than their line count
suggests: they are the difference between a user seeing "could not reach Skilljar v1:
[Errno 8] nodename nor servname provided" and seeing "Error executing tool list_paths".
"""
from __future__ import annotations

import base64
import copy
import json
import time

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar import exceptions as exc
from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import FakeBackend, V2Backend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import (
    V1_KEY_VAR,
    V2_ID_VAR,
    V2_SECRET_VAR,
    ClientProvider,
    CredentialPresence,
    settings_from_env,
    startup_warnings,
)
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend, V1Backend, V1Credentials, _page_of

KEY = "sk_test_key"


# --- transport ------------------------------------------------------------------------

@respx.mock
def test_a_network_failure_names_the_service_and_the_cause():
    """`httpx.ConnectError` on its own says nothing about WHO could not be reached, and the
    tool layer turns an untranslated error into "Error executing tool X" with the message
    discarded."""
    respx.route().mock(side_effect=httpx.ConnectError("nodename nor servname provided"))
    with pytest.raises(exc.ApiError, match="could not reach Skilljar v1"):
        V1Backend(V1Credentials(KEY)).list_paths()


@respx.mock
def test_an_http_error_carries_the_status_and_the_path():
    """The status is what tells a caller whether to retry, and the path is what tells them
    which of the fifteen calls behind a tool actually failed."""
    respx.route().mock(return_value=httpx.Response(503, json={"detail": "down"}))
    with pytest.raises(exc.ApiError, match="503") as caught:
        V1Backend(V1Credentials(KEY)).list_paths()
    assert caught.value.status == 503


def test_a_next_url_with_no_page_parameter_yields_no_page_number():
    """v1's `next` is a full URL and the page number is a query parameter in it. A `next`
    that carries none is not page 1 - it is a URL this parser cannot turn into a page, and
    guessing would send the caller round the first page for ever."""
    assert _page_of("https://api.skilljar.com/v1/paths/") is None
    assert _page_of("https://api.skilljar.com/v1/paths/?page=3") == 3


# --- the doubles describe themselves ---------------------------------------------------

def test_the_doubles_have_a_useful_repr():
    """A double that reprs as `<object at 0x10a...>` makes every failed assertion involving
    it unreadable, which is when a repr is the only thing anyone wants from it."""
    assert "FakeV1Backend(users=2)" == repr(
        FakeV1Backend(users=[{"id": "u1"}, {"id": "u2"}]))
    text = repr(Policy.from_profile("full"))
    assert text.startswith("Policy(")
    assert "may_contact_people=" in text


def test_a_private_attribute_is_an_attribute_error_not_a_policy_refusal():
    """`PolicyBackend.__getattr__` refuses any name with no declared gate. Dunder lookups go
    through the same path - `copy.deepcopy` asks for `__deepcopy__`, pickle asks for
    `__reduce_ex__` - and answering those with a PolicyError rather than AttributeError
    makes the object un-copyable and un-pickleable in a way that looks like a policy bug."""
    wrapped = PolicyBackend(FakeBackend(), Policy.from_profile("full"))

    with pytest.raises(AttributeError):
        _ = wrapped._not_a_real_private_attribute

    # The case that motivates it: `deepcopy` probes for `__deepcopy__` and `__reduce_ex__`,
    # and a PolicyError from either aborts the copy with a message about capabilities.
    assert copy.deepcopy(wrapped) is not wrapped

    # And the guard must not swallow the real refusal, which is a different answer to a
    # different question: this name HAS no gate, which is a bug in csa-skilljar rather than
    # a missing attribute, and the message says so.
    with pytest.raises(exc.PolicyError, match="no declared capability gate"):
        _ = wrapped.not_gated_at_all


# --- configuration ----------------------------------------------------------------------

def test_a_v1_key_builds_the_v1_backend_and_its_absence_does_not():
    """The v1 half is optional, and the two arms are what decides whether the v1-only tools
    raise a typed "set SKILLJAR_API_KEY" error or work."""
    env = {V2_ID_VAR: "id", V2_SECRET_VAR: "secret"}

    without = ClientProvider(settings_from_env(env))()
    with pytest.raises(exc.SkilljarError):
        without._require_v1()

    with_key = ClientProvider(settings_from_env({**env, V1_KEY_VAR: KEY}))()
    assert with_key._require_v1() is not None


def test_the_startup_warnings_name_each_missing_credential_separately():
    """Two independent credentials, so "something is missing" is not actionable: the user
    has to be told WHICH, and a single combined warning would send someone hunting for a v2
    problem when only v1 is unset."""
    both = " ".join(startup_warnings(CredentialPresence(v2=False, v1=False)))
    assert "v2" in both.lower() and "v1" in both.lower()

    only_v1 = startup_warnings(CredentialPresence(v2=True, v1=False))
    assert len(only_v1) == 1 and "v1" in only_v1[0].lower()

    assert startup_warnings(CredentialPresence(v2=True, v1=True)) == []


# --- the v2 wire ------------------------------------------------------------------------

def v2_credentials():
    """A token whose `scope` claim is absent, so the scope pre-check abstains and what is
    under test is the REQUEST rather than the permission. Same device as
    `test_v2_operation_census`."""
    def seg(payload):
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    token = f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600})}.sig"
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": token}))
    return V2Credentials("id", "sk-live-DEADBEEF")


@respx.mock
def test_a_student_update_by_email_sends_no_id():
    """`update_students` identifies a learner by `id` OR by `email`, and JSON:API says a
    resource object carries `id` only when it HAS one. Sending `"id": null` is a different
    request - it asks to update the student whose id is null - so the key has to be absent
    rather than empty."""
    route = respx.patch("https://api.skilljar.com/v2/students/").mock(
        return_value=httpx.Response(200, json={"data": []}))
    backend = V2Backend(v2_credentials())

    backend.update_students(items=[{"email": "a@example.org", "first_name": "A"},
                                   {"id": "s1", "first_name": "B"}])
    sent = json.loads(route.calls.last.request.content)["data"]
    assert "id" not in sent[0], "an update by email must not carry an id key at all"
    assert sent[1]["id"] == "s1"


@respx.mock
def test_a_non_json_body_is_an_error_only_when_the_status_is_not_a_success():
    """RFC 7009 says revoke returns no content, so an unparseable body on a 2xx is correct
    and must not be reported as a failure. The same body with a 500 is a failure, and the
    message has to say that the body was unparseable - otherwise the user is told a status
    code with no clue that the server sent something unreadable."""
    backend = V2Backend(v2_credentials())
    respx.post("https://api.skilljar.com/v2/auth/revoke").mock(
        return_value=httpx.Response(200, text=""))
    assert backend.revoke_refresh_token(token="rt")["data"]["type"] == "acknowledgement"

    respx.post("https://api.skilljar.com/v2/auth/revoke").mock(
        return_value=httpx.Response(502, text="<html>gateway</html>"))
    with pytest.raises(exc.ApiError, match="non-JSON body") as caught:
        backend.revoke_refresh_token(token="rt")
    assert caught.value.status == 502


# --- per-item batch errors ----------------------------------------------------------------

def test_the_same_bank_twice_in_one_batch_is_one_error_not_two_binds():
    """A duplicate inside a single batch cannot be caught by a uniqueness check against
    stored state - neither row exists yet when the batch arrives. It is reported against the
    SECOND occurrence with a pointer to it, so the first still binds and the caller is told
    exactly which element to remove."""
    backend = FakeBackend(
        quizzes=[{"type": "quizzes", "id": "qz1", "attributes": {"name": "Q"}}],
        question_banks=[{"type": "question-banks", "id": "qb1",
                         "attributes": {"name": "B"}}])
    data = backend.bind_banks(quiz_id="qz1",
                              items=[{"question_bank_id": "qb1"},
                                     {"question_bank_id": "qb1"}])["data"]
    assert data[0]["status"] != "error"
    assert data[1]["code"] == "duplicate_in_batch"
    assert data[1]["source"]["pointer"].startswith("/data/1/")


def test_a_purchase_is_found_past_the_first_row():
    """The loop's continue arm. A lookup that only ever ran against a one-row fixture would
    pass with `return` inside the loop body unconditionally."""
    v1 = FakeV1Backend(purchases=[{"id": "pu1"}, {"id": "pu2"}])
    assert v1.get_purchase(purchase_id="pu2")["rows"][0]["id"] == "pu2"
    with pytest.raises(exc.NotFoundError):
        v1.get_purchase(purchase_id="pu404")


# --- argument enumerations ------------------------------------------------------------

def test_an_unknown_progress_status_names_the_ones_that_exist():
    """A closed set of three, and the message lists them. `filter_progress_status` is
    comma-separated, so a caller who gets one of several values wrong needs to be told WHICH
    - listing only the valid set would leave them comparing by eye."""
    from .test_pagination import tools
    with pytest.raises(ToolError, match="not_a_status"):
        tools()[0]["list_enrollments"](filter_progress_status="completed,not_a_status")


def test_the_same_bank_twice_in_one_UPDATE_batch_is_also_one_error():
    """`bind_banks` and `update_bank_assignments` each keep their own `seen` set, so the
    duplicate rule is implemented twice and tested twice. Two copies of a rule is how one
    of them ends up different."""
    backend = FakeBackend(
        quizzes=[{"type": "quizzes", "id": "qz1", "attributes": {"name": "Q"}}],
        question_banks=[{"type": "question-banks", "id": "qb1",
                         "attributes": {"name": "B"}}])
    backend.bind_banks(quiz_id="qz1", items=[{"question_bank_id": "qb1"}])
    data = backend.update_bank_assignments(
        quiz_id="qz1", items=[{"question_bank_id": "qb1", "order": 1},
                              {"question_bank_id": "qb1", "order": 2}])["data"]
    assert data[0]["status"] != "error"
    assert data[1]["code"] == "duplicate_in_batch"
    assert data[1]["source"]["pointer"] == "/data/1/attributes/question_bank_id"


def test_a_valid_progress_status_is_passed_through():
    """The other arm. A guard that rejected every value would pass the case above and break
    the filter entirely, and nothing would distinguish the two."""
    from .test_pagination import tools
    out = tools()[0]["list_enrollments"](filter_progress_status="completed")
    assert "enrollments" in out


def test_a_registered_client_reports_only_the_keys_the_server_returned():
    """The registration response is the ONE time the secret is visible, so the serialiser
    copies a fixed key list rather than the whole payload - and a server that omits an
    optional field must not produce a null the caller could mistake for a value it was
    issued."""
    class Sparse:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            attr = getattr(self._inner, name)
            if name != "register_oauth_client":
                return attr

            def only_the_essentials(**kwargs):
                env = attr(**kwargs)
                keep = {"client_id", "client_secret", "client_name"}
                return {**env, "data": {k: v for k, v in env["data"].items() if k in keep}}
            return only_the_essentials

    # An orange-line tool: it weakens the controls around it, so the capability alone does
    # not reach it and it has to be named in a second setting. Exactly the refusal
    # DEC-016 asks for, and the test has to opt in the way an operator would.
    policy = Policy.from_profile("full", orange_allowed={"register_oauth_client"})
    client = SkilljarClient(PolicyBackend(Sparse(FakeBackend()), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    out = fns["register_oauth_client"](client_name="C")
    assert out["client_id"]
    for absent in ("redirect_uris", "grant_types", "token_endpoint_auth_method", "scope"):
        assert absent not in out


def test_an_asset_page_with_no_count_omits_total():
    """v1's two envelopes again, on the one v1 tool that is not in the paged census because
    it returns the whole asset library in a single response."""
    class NoCount:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            attr = getattr(self._inner, name)
            if name != "list_assets":
                return attr
            return lambda **kw: {**attr(**kw), "total": None}

    policy = Policy.from_profile("full")
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy),
                            v1=PolicyBackend(NoCount(FakeV1Backend(assets=[{"id": "a1"}])),
                                             policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    out = fns["list_assets"]()
    assert out["assets"]
    assert "total" not in out


def test_an_override_without_timestamps_reports_none():
    """`created_at` and `updated_at` are server-set, so a row read back before they are
    populated - or from a sparse fieldset - has neither."""
    class NoTimestamps:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            attr = getattr(self._inner, name)
            if name != "list_visibility_overrides":
                return attr

            def stripped(**kwargs):
                env = attr(**kwargs)
                rows = [{**r, "attributes": {k: v for k, v in r["attributes"].items()
                                             if k not in ("created_at", "updated_at")}}
                        for r in env.get("data", [])]
                return {**env, "data": rows}
            return stripped

    inner = FakeBackend(groups=[{"type": "groups", "id": "g1",
                                 "attributes": {"name": "G"}}])
    inner.add_visibility_overrides(group_id="g1", items=[{"published_course_id": "pc1"}])
    policy = Policy.from_profile("full")
    client = SkilljarClient(PolicyBackend(NoTimestamps(inner), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    row = fns["list_visibility_overrides"](id="g1")["overrides"][0]
    assert row["published_course_id"] == "pc1"
    assert "created_at" not in row and "updated_at" not in row


# --- the two seams --------------------------------------------------------------------

def test_the_run_seam_actually_starts_the_server(monkeypatch):
    """`_run_server` exists so `test_cli` can stub the blocking `run()` call - and stubbing
    it everywhere left the seam itself, the two lines that build the server and start the
    transport, never executed. A seam that no test drives is a seam that can be broken by
    a rename with the whole CLI suite still green."""
    from csa_skilljar.mcp import cli

    started: dict[str, object] = {}

    class Stub:
        def run(self, transport):
            started["transport"] = transport

    monkeypatch.setattr(cli, "create_server", lambda provider, settings: Stub())
    cli._run_server(cli.Settings(), lambda: None)
    assert started["transport"] == "stdio", "the server must be started on stdio"


def test_the_plan_predicts_scope_refusals_and_survives_having_no_credential(monkeypatch):
    """Two arms of the same block.

    The plan predicts refusals from BOTH the local capability profile and the credential's
    OAuth scopes - a first live run predicted zero and then hit two, because the policy
    allowed the call and the scope pre-check stopped it.

    Reading the scopes means touching the credential, which is exactly what is absent or
    broken when someone runs the demo to find out why nothing works. So the read is wrapped,
    and this asserts the plan still comes back rather than failing with the thing it was
    called to diagnose."""
    from csa_skilljar.client import SkilljarClient as _Client

    policy = Policy.from_profile("full")
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy))

    # No credential to read: the demo must still produce a plan.
    monkeypatch.setattr(type(client), "credentials",
                        property(lambda self: (_ for _ in ()).throw(
                            exc.CredentialsMissing("no credential configured"))),
                        raising=False)
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    plan = fns["demonstration_plan"]()
    assert plan["steps"], "a missing credential must not cost the caller the plan"

    # And with a NARROW profile plus a credential granting nothing, the two reasons
    # overlap. `already` is what stops a step refused by the capability profile being
    # reported a second time under the scope reason - which would make one blockage look
    # like two and inflate the number the demo exists to report honestly.
    class NoScopes:
        def granted_scopes(self):
            return []

    narrow = Policy.from_profile("reporting")      # 3 capabilities of 21
    narrow_client = SkilljarClient(PolicyBackend(FakeBackend(), narrow))
    monkeypatch.setattr(type(narrow_client), "credentials",
                        property(lambda self: NoScopes()), raising=False)
    app = create_server(lambda: narrow_client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    plan = fns["demonstration_plan"]()

    refused = plan["will_be_refused"]
    by_profile = [r["tool"] for r in refused if r["refused_by"] == "capability profile"]
    assert by_profile, "a three-capability profile must refuse some of the plan"
    tools_refused = [r["tool"] for r in refused]
    assert len(tools_refused) == len(set(tools_refused)), (
        "a step blocked by both the profile and the scopes was reported twice")
    assert _Client is SkilljarClient
