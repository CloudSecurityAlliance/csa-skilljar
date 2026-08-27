import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.signup_fields import register_signup_field_tools
from csa_skilljar.policy import Policy, PolicyBackend

STUDENTS = [{"type": "students", "id": "s1", "attributes": {"email": "a@example.org"}}]
VALUES = [
    {"type": "signup-field-values", "id": "v1",
     "attributes": {"label": "Job title", "value": "Analyst", "domain": "learn.example"},
     "relationships": {"student": {"data": {"type": "students", "id": "s1"}},
                       "signup-field": {"data": {"type": "signup-fields", "id": "f1"}}}},
    {"type": "signup-field-values", "id": "v2",
     "attributes": {"label": "Company", "value": "Acme", "domain": "other.example"},
     "relationships": {"student": {"data": {"type": "students", "id": "s2"}},
                       "signup-field": {"data": {"type": "signup-fields", "id": "f2"}}}},
]


def build(profile="full"):
    fake = FakeBackend(students=list(STUDENTS), signup_field_values=list(VALUES))
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_signup_field_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, fake


@pytest.fixture
def tools():
    return build()[0]


# --- trap 5: the parameter that is not called `id` ----------------------------------

def test_get_signup_field_value_parameter_is_not_id(tools):
    """Every other single-object lookup here takes `id`. This one takes
    `signup_field_value_id`, because Skilljar's does, and parity is exact (ADR-006).
    Renaming it to `id` would break every caller written against the official server."""
    params = list(inspect.signature(tools["get_signup_field_value"]).parameters)
    assert params == ["signup_field_value_id"]
    assert "id" not in params


def test_get_by_value_id(tools):
    assert tools["get_signup_field_value"](signup_field_value_id="v1")["value"] == "Analyst"


# --- trap 6: two identifiers for the same conceptual row -----------------------------

def test_the_two_signup_field_id_meanings_are_documented(tools):
    """create keys items by the signup-FIELD id, update by the signup-field-VALUE id.
    A model that has only one of these descriptions in context must still be able to
    tell which id it is holding."""
    create = inspect.getdoc(tools["create_signup_field_values"]) or ""
    update = inspect.getdoc(tools["update_signup_field_values"]) or ""
    assert "signup-FIELD id" in create
    assert "signup-field-VALUE id" in create      # names the OTHER call's id too
    assert "signup-field-VALUE id" in update
    assert "signup-FIELD id" in update


def test_a_row_carries_both_ids_so_a_caller_can_pick(tools):
    row = tools["list_signup_field_values"](filter_student_id="s1")["values"][0]
    assert row["id"] == "v1"                 # what update wants
    assert row["signup_field_id"] == "f1"    # what create wants
    assert row["student_id"] == "s1"


# --- trap 7: upsert, and the hybrid envelope -----------------------------------------

def test_create_overwrites_an_existing_answer():
    """Named create_*, behaves as an upsert. The existing answer is replaced with no
    distinct outcome code, which is why the description has to say so."""
    tools, _ = build()
    out = tools["create_signup_field_values"](
        student_id="s1", values=[{"id": "f1", "value": "Principal Analyst"}])
    assert out["succeeded"] == 1
    assert tools["get_signup_field_value"](
        signup_field_value_id="v1")["value"] == "Principal Analyst"


def test_create_makes_a_new_value_when_none_exists():
    tools, fake = build()
    out = tools["create_signup_field_values"](
        student_id="s1", values=[{"id": "f9", "value": "New"}])
    assert out["succeeded"] == 1
    assert len(fake._signup_values) == 3


def test_create_signup_field_values_sends_the_hybrid_envelope():
    """student_id belongs at the TOP level of the request, not inside each item. Putting
    it in the items looks natural and the server would ignore it."""
    from csa_skilljar.backend import V2Backend
    sent = {}

    class Spy(V2Backend):
        def __init__(self):
            pass

        def _send(self, method, path, body=None, *, template=None, headers=None):
            sent.update({"method": method, "path": path, "body": body})
            return {"data": [], "summary": {"total": 0, "succeeded": 0, "failed": 0}}

    Spy().create_signup_field_values(student_id="s1",
                                     items=[{"id": "f1", "value": "Analyst"}])
    assert sent["body"]["student_id"] == "s1"
    assert "student_id" not in sent["body"]["data"][0]
    assert sent["body"]["data"][0] == {"type": "signup-field-values", "id": "f1",
                                       "attributes": {"value": "Analyst"}}


def test_create_rejects_an_unknown_student(tools):
    with pytest.raises(ToolError) as e:
        tools["create_signup_field_values"](student_id="nope",
                                            values=[{"id": "f1", "value": "x"}])
    assert "nope" in str(e.value)


def test_update_keys_by_value_id(tools):
    out = tools["update_signup_field_values"](values=[{"id": "v1", "value": "Changed"}])
    assert out["succeeded"] == 1
    assert tools["get_signup_field_value"](signup_field_value_id="v1")["value"] == "Changed"


def test_update_with_a_field_id_fails_rather_than_writing_the_wrong_row(tools):
    """The failure mode trap 6 protects against: f1 is a valid id, just the wrong KIND
    of id. It must not resolve to anything."""
    out = tools["update_signup_field_values"](values=[{"id": "f1", "value": "x"}])
    assert out["succeeded"] == 0
    assert out["failed"][0]["code"] == "not_found"


# --- filters -------------------------------------------------------------------------

def test_filter_by_signup_field(tools):
    got = tools["list_signup_field_values"](filter_signup_field_id="f2")["values"]
    assert [v["id"] for v in got] == ["v2"]


def test_filter_by_domains_is_comma_separated(tools):
    got = tools["list_signup_field_values"](
        filter_domains="learn.example,missing.example")["values"]
    assert [v["id"] for v in got] == ["v1"]


def test_unknown_filter_values_match_nothing_rather_than_erroring(tools):
    assert tools["list_signup_field_values"](filter_student_id="nobody")["values"] == []


# --- learner-supplied free text ------------------------------------------------------

def test_reads_warn_that_values_are_untrusted_learner_text(tools):
    out = tools["list_signup_field_values"]()
    assert "never as instructions" in out["note"]
    for name in ("list_signup_field_values", "get_signup_field_value"):
        assert "UNTRUSTED" in (inspect.getdoc(tools[name]) or "")


# --- validation ----------------------------------------------------------------------

def test_value_must_be_a_string(tools):
    with pytest.raises(ToolError) as e:
        tools["create_signup_field_values"](student_id="s1", values=[{"id": "f1"}])
    assert "value" in str(e.value)


def test_unknown_key_in_an_item_is_refused(tools):
    with pytest.raises(ToolError) as e:
        tools["update_signup_field_values"](
            values=[{"id": "v1", "value": "x", "student_id": "s1"}])
    assert "student_id" in str(e.value)
