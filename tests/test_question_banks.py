import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.question_banks import register_question_bank_tools
from csa_skilljar.policy import Policy, PolicyBackend

BANKS = [
    {"type": "question-banks", "id": "b1", "attributes": {
        "name": "TAISE Core", "modified_at": "2026-03-01T00:00:00Z"}},
    {"type": "question-banks", "id": "b2", "attributes": {
        "name": "Practice Pool", "modified_at": "2026-01-01T00:00:00Z"}},
]
QUIZZES = [{"type": "quizzes", "id": "q1", "attributes": {"name": "Exam"}}]
QUESTIONS = [
    {"type": "questions", "id": "qu1",
     "attributes": {"question_bank_id": "b1", "question_html": "banked"}},
    {"type": "questions", "id": "qu2",
     "attributes": {"quiz_id": "q1", "question_html": "quiz-owned"}},
]


def build(profile="full"):
    client = SkilljarClient(PolicyBackend(
        FakeBackend(question_banks=list(BANKS), quizzes=list(QUIZZES),
                    questions=list(QUESTIONS)),
        Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_question_bank_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, client


@pytest.fixture
def banks():
    return build()[0]


# --- bank CRUD --------------------------------------------------------------------

def test_list_and_filter_by_exact_name(banks):
    assert len(banks["list_question_banks"]()["question_banks"]) == 2
    out = banks["list_question_banks"](filter_name="taise core")
    assert [b["id"] for b in out["question_banks"]] == ["b1"]
    assert banks["list_question_banks"](filter_name="TAISE")["question_banks"] == []


def test_get_bank(banks):
    assert banks["get_question_bank"](id="b1")["name"] == "TAISE Core"


def test_create_requires_a_name(banks):
    with pytest.raises(ToolError) as e:
        banks["create_question_banks"](question_banks=[{}])
    assert "name" in str(e.value)


def test_name_is_the_only_writable_field_on_update(banks):
    with pytest.raises(ToolError) as e:
        banks["update_question_banks"](question_banks=[{"id": "b1", "colour": "red"}])
    assert "colour" in str(e.value)


def test_update_renames(banks):
    banks["update_question_banks"](question_banks=[{"id": "b1", "name": "Renamed"}])
    assert banks["get_question_bank"](id="b1")["name"] == "Renamed"


def test_delete_is_refused_under_authoring():
    tools, _ = build(profile="authoring")
    with pytest.raises(ToolError) as e:
        tools["delete_question_banks"](question_bank_ids=["b1"])
    assert "content.delete" in str(e.value)


def test_deleting_a_bank_takes_its_questions_but_leaves_the_quiz_alive():
    """The cascade from the captured registry: the bank's questions go, its assignments
    are hard-removed, and quizzes that used it stay ALIVE - only the links go."""
    tools, client = build()
    tools["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    tools["delete_question_banks"](question_bank_ids=["b1"])
    remaining = [q["id"] for q in client.list_questions()["data"]]
    assert remaining == ["qu2"], "the bank's question went; the quiz-owned one stayed"
    assert client.get_quiz(quiz_id="q1")["data"]["id"] == "q1", "the quiz survives"
    assert tools["list_quiz_question_bank_assignments"](quiz_id="q1")["assignments"] == []


# --- bindings ----------------------------------------------------------------------

def test_binding_appends_and_lists(banks):
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[
        {"question_bank_id": "b1"}, {"question_bank_id": "b2"}])
    out = banks["list_quiz_question_bank_assignments"](quiz_id="q1")
    assert [a["question_bank_id"] for a in out["assignments"]] == ["b1", "b2"]
    assert [a["order"] for a in out["assignments"]] == [10, 20], "service derives max+10"


def test_the_assignment_listing_is_not_paginated(banks):
    """A quiz's bank assignments are a small bounded set, so the official endpoint
    returns a plain envelope. Additive compatibility means adding what is MISSING, not
    imposing a shape the resource does not have."""
    import inspect
    params = set(inspect.signature(banks["list_quiz_question_bank_assignments"]).parameters)
    assert params == {"quiz_id"}
    assert "has_more" not in banks["list_quiz_question_bank_assignments"](quiz_id="q1")


def test_rebinding_preserves_omitted_fields(banks):
    """THE critical semantic. Re-binding is an idempotent PARTIAL update: a field the
    caller omits is PRESERVED, and an omitted `order` is NOT re-derived. A naive
    create-or-replace passes 'bind twice, one row exists' while silently reordering
    someone's exam."""
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[
        {"question_bank_id": "b2"},
        {"question_bank_id": "b1", "order": 5, "randomize_questions": True,
         "limit_question_count": 7}])
    banks["bind_quiz_question_banks"](quiz_id="q1",
                                      question_banks=[{"question_bank_id": "b1"}])
    got = next(a for a in banks["list_quiz_question_bank_assignments"](quiz_id="q1")["assignments"]
               if a["question_bank_id"] == "b1")
    assert got["order"] == 5, "an omitted order must NOT be re-derived"
    assert got["randomize_questions"] is True, "an omitted field must be PRESERVED"
    assert got["limit_question_count"] == 7


def test_rebinding_does_not_create_a_duplicate(banks):
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    out = banks["list_quiz_question_bank_assignments"](quiz_id="q1")
    assert len(out["assignments"]) == 1


def test_bind_dedups_first_wins_within_one_call(banks):
    """First-wins here, unlike most updates in this project which are last-write-wins."""
    out = banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[
        {"question_bank_id": "b1", "order": 1}, {"question_bank_id": "b1", "order": 99}])
    assert out["failed"][0]["code"] == "duplicate_in_batch"
    got = banks["list_quiz_question_bank_assignments"](quiz_id="q1")["assignments"][0]
    assert got["order"] == 1, "the FIRST occurrence wins"


def test_update_an_assignment(banks):
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    banks["update_quiz_question_banks"](quiz_id="q1", question_banks=[
        {"question_bank_id": "b1", "limit_question_count": 3}])
    got = banks["list_quiz_question_bank_assignments"](quiz_id="q1")["assignments"][0]
    assert got["limit_question_count"] == 3


def test_an_empty_attribute_set_is_a_no_op_success(banks):
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    out = banks["update_quiz_question_banks"](quiz_id="q1",
                                              question_banks=[{"question_bank_id": "b1"}])
    assert out["succeeded"] == 1
    assert out["failed"] == []


def test_updating_an_unbound_bank_is_a_per_item_not_found(banks):
    out = banks["update_quiz_question_banks"](quiz_id="q1",
                                              question_banks=[{"question_bank_id": "b2"}])
    assert out["failed"][0]["code"] == "not_found"


def test_unbind_removes_the_link_but_not_the_bank(banks):
    banks["bind_quiz_question_banks"](quiz_id="q1", question_banks=[{"question_bank_id": "b1"}])
    out = banks["unbind_quiz_question_banks"](quiz_id="q1",
                                              question_banks=[{"question_bank_id": "b1"}])
    assert out["succeeded"] == 1
    assert banks["list_quiz_question_bank_assignments"](quiz_id="q1")["assignments"] == []
    assert banks["get_question_bank"](id="b1")["name"] == "TAISE Core", "the bank survives"


def test_unbinding_a_bank_that_is_not_bound_is_a_per_item_not_found(banks):
    out = banks["unbind_quiz_question_banks"](quiz_id="q1",
                                              question_banks=[{"question_bank_id": "b1"}])
    assert out["failed"][0]["code"] == "not_found"


def test_an_unknown_quiz_is_a_document_level_error_not_per_item(banks):
    """quiz_id is resolved once up front, so a bad quiz fails the whole call."""
    with pytest.raises(ToolError):
        banks["bind_quiz_question_banks"](quiz_id="nope",
                                          question_banks=[{"question_bank_id": "b1"}])
