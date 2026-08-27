import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.students import register_student_tools
from csa_skilljar.policy import Policy, PolicyBackend

STUDENTS = [
    {"type": "students", "id": "s1", "attributes": {
        "email": "ada@example.org", "first_name": "Ada", "last_name": "Lovelace",
        "is_inactive": False, "date_joined": "2026-01-01T00:00:00Z"}},
    {"type": "students", "id": "s2", "attributes": {
        "email": "grace@example.org", "first_name": "Grace", "last_name": "Hopper",
        "is_inactive": True}},
]


def build(profile="full"):
    client = SkilljarClient(PolicyBackend(FakeBackend(students=list(STUDENTS)),
                                          Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_student_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- reads and ordinary writes -----------------------------------------------------

def test_email_filter_is_exact_and_case_insensitive(tools):
    assert [s["id"] for s in tools["list_students"](filter_email="ADA@example.org")["students"]] == ["s1"]
    assert tools["list_students"](filter_email="ada")["students"] == []


def test_filter_inactive(tools):
    assert [s["id"] for s in tools["list_students"](filter_is_inactive=True)["students"]] == ["s2"]


def test_get_student(tools):
    assert tools["get_student"](id="s1")["email"] == "ada@example.org"


def test_create_dedups_first_wins_on_email(tools):
    out = tools["create_students"](students=[
        {"email": "new@example.org"}, {"email": "NEW@EXAMPLE.ORG"}])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "duplicate_in_batch"


def test_create_rejects_a_non_email(tools):
    with pytest.raises(ToolError) as e:
        tools["create_students"](students=[{"email": "nope"}])
    assert "nope" in str(e.value)


def test_names_are_length_bounded(tools):
    with pytest.raises(ToolError) as e:
        tools["create_students"](students=[{"email": "a@example.org", "first_name": "x" * 51}])
    assert "50" in str(e.value)


# --- update: dual identifier, read-only email, the two-PATCH rule ------------------

def test_update_needs_an_id_or_an_email(tools):
    with pytest.raises(ToolError) as e:
        tools["update_students"](students=[{"first_name": "X"}])
    assert "id" in str(e.value) and "email" in str(e.value)


def test_update_by_email_when_no_id_is_given(tools):
    out = tools["update_students"](students=[
        {"email": "ada@example.org", "first_name": "Augusta"}])
    assert out["succeeded"] == 1
    assert tools["get_student"](id="s1")["first_name"] == "Augusta"


def test_email_is_a_confirmation_when_an_id_is_present(tools):
    """Passing both is how a caller says 'update this id, and fail if it is not who I
    think it is'. A mismatch is a per-item validation_error, not a silent write."""
    out = tools["update_students"](students=[
        {"id": "s1", "email": "grace@example.org", "first_name": "Wrong"}])
    assert out["succeeded"] == 0
    assert out["failed"][0]["code"] == "validation_error"
    assert tools["get_student"](id="s1")["first_name"] == "Ada", "nothing was written"


def test_a_matching_email_confirmation_permits_the_write(tools):
    out = tools["update_students"](students=[
        {"id": "s1", "email": "ada@example.org", "first_name": "Augusta"}])
    assert out["succeeded"] == 1


def test_reactivating_and_editing_in_one_call_is_refused(tools):
    """The API accepts a combined PATCH and silently does not apply the other fields.
    Rejecting locally is the ADR-008 reasoning again."""
    with pytest.raises(ToolError) as e:
        tools["update_students"](students=[
            {"id": "s2", "is_inactive": False, "first_name": "Grace B"}])
    msg = str(e.value).lower()
    assert "two" in msg or "separate" in msg
    assert "is_inactive" in msg


def test_deactivating_and_editing_in_one_call_is_allowed(tools):
    """Only REACTIVATION has the two-PATCH rule."""
    out = tools["update_students"](students=[
        {"id": "s1", "is_inactive": True, "first_name": "Ada B"}])
    assert out["succeeded"] == 1


# --- the four that cannot be undone -------------------------------------------------

@pytest.mark.parametrize("tool,kwargs", [
    ("anonymize_student", {"id": "s1", "confirm": True}),
    ("deactivate_student", {"id": "s1"}),
    ("set_student_password", {"id": "s1", "password": "hunter2hunter2", "confirm": True}),
    ("send_password_reset", {"id": "s1", "domain": "learn.example.org"}),
])
def test_destructive_tools_are_refused_under_the_people_profile(tool, kwargs):
    """`people` grants read and write. A credential for routine learner administration
    must not be able to erase anyone."""
    with pytest.raises(ToolError) as e:
        build(profile="people")[tool](**kwargs)
    assert "people.destructive" in str(e.value)


def test_ordinary_writes_are_permitted_under_the_people_profile():
    out = build(profile="people")["create_students"](students=[{"email": "x@example.org"}])
    assert out["succeeded"] == 1


def test_anonymize_requires_explicit_confirmation(tools):
    with pytest.raises(ToolError) as e:
        tools["anonymize_student"](id="s1")
    msg = str(e.value)
    assert "confirm" in msg
    assert "irreversible" in msg.lower() or "cannot be undone" in msg.lower()
    assert tools["get_student"](id="s1")["email"] == "ada@example.org", "nothing erased"


def test_confirm_defaults_to_false(tools):
    assert inspect.signature(tools["anonymize_student"]).parameters["confirm"].default is False
    assert inspect.signature(tools["set_student_password"]).parameters["confirm"].default is False


def test_anonymize_erases_the_pii(tools):
    out = tools["anonymize_student"](id="s1", confirm=True)
    assert out["anonymized"] is True
    assert "ada@example.org" not in str(tools["get_student"](id="s1"))


def test_set_password_requires_confirmation_and_a_long_enough_password(tools):
    with pytest.raises(ToolError) as e:
        tools["set_student_password"](id="s1", password="hunter2hunter2")
    assert "confirm" in str(e.value)
    with pytest.raises(ToolError) as e:
        tools["set_student_password"](id="s1", password="short", confirm=True)
    assert "password" in str(e.value).lower()


def test_the_password_value_never_appears_in_an_error(tools):
    with pytest.raises(ToolError) as e:
        tools["set_student_password"](id="nope", password="sk-live-SECRET-PW", confirm=True)
    assert "sk-live-SECRET-PW" not in str(e.value)


def test_password_reset_requires_a_domain(tools):
    with pytest.raises(TypeError):
        tools["send_password_reset"](id="s1")
    out = tools["send_password_reset"](id="s1", domain="learn.example.org")
    assert out["sent"] is True


def test_deactivate_does_not_touch_enrollments(tools):
    out = tools["deactivate_student"](id="s1")
    assert out["deactivated"] is True
    assert "enrol" in out["note"].lower() or "enroll" in out["note"].lower()
