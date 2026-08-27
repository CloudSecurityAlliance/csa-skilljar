import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.questions import register_question_tools
from csa_skilljar.policy import Policy, PolicyBackend

QUESTIONS = [
    {"type": "questions", "id": "qu1", "attributes": {
        "question_html": "<p>What is ZT?</p>", "question_type": "MULTIPLE_CHOICE",
        "quiz_id": "q1", "order": 10,
        "answers": [{"answer_text": "A", "correct": True},
                    {"answer_text": "B", "correct": False}]}},
    {"type": "questions", "id": "qu2", "attributes": {
        "question_html": "<p>Explain.</p>", "question_type": "FREEFORM",
        "question_bank_id": "b1", "order": 10, "answers": []}},
]

MC = {"question_html": "<p>Q?</p>", "question_type": "MULTIPLE_CHOICE", "quiz_id": "q1",
      "answers": [{"answer_text": "A", "correct": True}]}


def build(profile="full"):
    client = SkilljarClient(PolicyBackend(FakeBackend(questions=list(QUESTIONS)),
                                          Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_question_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def questions():
    return build()


# --- reads ------------------------------------------------------------------------

def test_filter_by_quiz(questions):
    assert [q["id"] for q in questions["list_questions"](filter_quiz_id="q1")["questions"]] == ["qu1"]


def test_filter_by_question_bank(questions):
    out = questions["list_questions"](filter_question_bank_id="b1")
    assert [q["id"] for q in out["questions"]] == ["qu2"]


def test_get_question_nests_answers_inline(questions):
    out = questions["get_question"](id="qu1")
    assert len(out["answers"]) == 2
    assert out["answers"][0]["answer_text"] == "A"


# --- create: the XOR and answer-shape rules ----------------------------------------

def test_a_question_needs_exactly_one_parent(questions):
    for attrs, why in (
        ({**MC, "question_bank_id": "b1"}, "both"),
        ({k: v for k, v in MC.items() if k != "quiz_id"}, "neither"),
    ):
        with pytest.raises(ToolError) as e:
            questions["create_questions"](questions=[attrs])
        assert "quiz_id" in str(e.value) and "question_bank_id" in str(e.value), why


def test_freeform_must_have_no_answers(questions):
    with pytest.raises(ToolError) as e:
        questions["create_questions"](questions=[
            {**MC, "question_type": "FREEFORM",
             "answers": [{"answer_text": "A"}]}])
    assert "FREEFORM" in str(e.value)


def test_non_freeform_needs_at_least_one_answer(questions):
    with pytest.raises(ToolError) as e:
        questions["create_questions"](questions=[{**MC, "answers": []}])
    assert "at least one answer" in str(e.value).lower()


def test_only_four_question_types_are_enabled(questions):
    with pytest.raises(ToolError) as e:
        questions["create_questions"](questions=[{**MC, "question_type": "LINEAR_SCALE"}])
    assert "MULTIPLE_CHOICE" in str(e.value)


def test_fields_the_service_assigns_are_rejected_not_dropped(questions):
    for field in ("order", "is_graded", "is_optional", "answer_feedback_html"):
        with pytest.raises(ToolError) as e:
            questions["create_questions"](questions=[{**MC, field: 1}])
        assert field in str(e.value)


def test_answer_text_is_required_and_bounded(questions):
    with pytest.raises(ToolError) as e:
        questions["create_questions"](questions=[{**MC, "answers": [{"correct": True}]}])
    assert "answer_text" in str(e.value)
    with pytest.raises(ToolError) as e:
        questions["create_questions"](questions=[
            {**MC, "answers": [{"answer_text": "x" * 1001}]}])
    assert "1000" in str(e.value)


def test_a_valid_question_is_created(questions):
    out = questions["create_questions"](questions=[MC])
    assert out["succeeded"] == 1


# --- update: answers immutable, read-only fields -----------------------------------

def test_answers_cannot_be_updated(questions):
    """Answers are IMMUTABLE on update - there is no `answers` field. A model that
    thinks it changed an exam's answers and did not is the failure to avoid."""
    with pytest.raises(ToolError) as e:
        questions["update_questions"](questions=[
            {"id": "qu1", "answers": [{"answer_text": "New"}]}])
    msg = str(e.value)
    assert "immutable" in msg.lower()
    assert "delete" in msg.lower(), "the message must say how to actually change them"


@pytest.mark.parametrize("field", ["question_type", "quiz_id", "question_bank_id", "order"])
def test_read_only_fields_are_rejected(questions, field):
    with pytest.raises(ToolError) as e:
        questions["update_questions"](questions=[{"id": "qu1", field: "x"}])
    assert "read-only" in str(e.value).lower()


def test_a_normal_update_works(questions):
    out = questions["update_questions"](questions=[
        {"id": "qu1", "question_html": "<p>Changed</p>"}])
    assert out["succeeded"] == 1
    assert questions["get_question"](id="qu1")["question_html"] == "<p>Changed</p>"


# --- delete -------------------------------------------------------------------------

def test_delete_is_refused_under_authoring():
    with pytest.raises(ToolError) as e:
        build(profile="authoring")["delete_questions"](question_ids=["qu1"])
    assert "content.delete" in str(e.value)


def test_delete_removes_the_question(questions):
    out = questions["delete_questions"](question_ids=["qu1"])
    assert out["succeeded"] == 1
    with pytest.raises(ToolError):
        questions["get_question"](id="qu1")


# --- the three captured quirks, each guarded ---------------------------------------

def test_fill_in_the_blank_forces_every_answer_correct(questions):
    """From the captured registry: `correct` is accepted for a uniform wire shape and
    then FORCED True for this type. A caller who sent correct=False and believes it
    took effect has a wrong mental model of their own exam."""
    made = questions["create_questions"](questions=[{
        "question_html": "<p>The capital of France is ___</p>",
        "question_type": "FILL_IN_THE_BLANK", "quiz_id": "q1",
        "answers": [{"answer_text": "Paris", "correct": False}]}])
    answer = questions["get_question"](id=made["ids"][0])["answers"][0]
    assert answer["correct"] is True


def test_answer_order_is_assigned_by_position(questions):
    made = questions["create_questions"](questions=[{
        **MC, "answers": [{"answer_text": "A"}, {"answer_text": "B"}, {"answer_text": "C"}]}])
    orders = [a["order"] for a in questions["get_question"](id=made["ids"][0])["answers"]]
    assert orders == [0, 10, 20], "idx*10 by array position"


def test_a_stored_type_conflict_fails_that_row_not_the_batch(questions):
    """The first validation that CANNOT be done locally: the schema cannot see the
    stored question_type, so this is a per-item validation_error inside a 207 rather
    than a document-level 422. Do not pre-check it - that is N+1 requests and a race."""
    out = questions["update_questions"](questions=[
        {"id": "qu1", "question_html": "<p>fine</p>"},
        {"id": "qu1", "case_sensitive": True}])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "validation_error"
    assert "FILL_IN_THE_BLANK" in out["failed"][0]["detail"]
