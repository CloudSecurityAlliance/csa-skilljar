import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.quizzes import register_quiz_tools
from csa_skilljar.policy import Policy, PolicyBackend

QUIZZES = [
    {"type": "quizzes", "id": "q1", "attributes": {
        "name": "Zero Trust Exam", "description_html": "<p>d</p>", "alignment": "center",
        "passing_percentage_correct": 70, "max_attempts": 3, "randomize_questions": True,
        "modified_at": "2026-03-01T00:00:00Z"}},
    {"type": "quizzes", "id": "q2", "attributes": {
        "name": "Practice", "passing_percentage_correct": 0,
        "modified_at": "2026-01-01T00:00:00Z"}},
]


def build(profile="full", quizzes=QUIZZES):
    client = SkilljarClient(PolicyBackend(FakeBackend(quizzes=list(quizzes)),
                                          Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_quiz_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def quizzes():
    return build()


# --- reads ------------------------------------------------------------------------

def test_list_quizzes_returns_all(quizzes):
    assert len(quizzes["list_quizzes"]()["quizzes"]) == 2


def test_filter_name_is_exact_and_case_insensitive(quizzes):
    assert quizzes["list_quizzes"](filter_name="zero trust exam")["quizzes"][0]["id"] == "q1"
    assert quizzes["list_quizzes"](filter_name="Zero")["quizzes"] == []


def test_filter_updated_since_narrows(quizzes):
    out = quizzes["list_quizzes"](filter_updated_since="2026-02-01T00:00:00Z")
    assert [q["id"] for q in out["quizzes"]] == ["q1"]


def test_official_argument_names(quizzes):
    params = set(inspect.signature(quizzes["list_quizzes"]).parameters)
    assert {"filter_name", "filter_updated_since"} <= params
    assert {"page_cursor", "page_size"} <= params, "our additive extension"


def test_get_quiz_returns_the_settings(quizzes):
    out = quizzes["get_quiz"](id="q1")
    assert out["passing_percentage_correct"] == 70
    assert out["max_attempts"] == 3
    assert out["randomize_questions"] is True


def test_get_quiz_unknown_id(quizzes):
    with pytest.raises(ToolError):
        quizzes["get_quiz"](id="nope")


# --- writes -----------------------------------------------------------------------

def test_create_requires_a_name(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["create_quizzes"](quizzes=[{"description_html": "<p>x</p>"}])
    assert "name" in str(e.value)


def test_create_rejects_an_unknown_attribute(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["create_quizzes"](quizzes=[{"name": "Q", "colour": "blue"}])
    assert "colour" in str(e.value)


def test_passing_percentage_is_validated_locally(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["create_quizzes"](quizzes=[{"name": "Q", "passing_percentage_correct": 101}])
    assert "0" in str(e.value) and "100" in str(e.value)


def test_time_limit_upper_bound_is_validated_locally(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["create_quizzes"](quizzes=[{"name": "Q", "time_limit_seconds": 3600001}])
    assert "3600000" in str(e.value)


def test_a_valid_quiz_is_created(quizzes):
    out = quizzes["create_quizzes"](quizzes=[{"name": "New", "max_attempts": 0}])
    assert out["succeeded"] == 1
    assert quizzes["get_quiz"](id=out["ids"][0])["name"] == "New"


def test_update_preserves_omitted_fields(quizzes):
    quizzes["update_quizzes"](quizzes=[{"id": "q1", "name": "Renamed"}])
    got = quizzes["get_quiz"](id="q1")
    assert got["name"] == "Renamed"
    assert got["passing_percentage_correct"] == 70, "omitted fields are preserved"


def test_update_requires_an_id(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["update_quizzes"](quizzes=[{"name": "X"}])
    assert "id" in str(e.value)


# --- delete: the first destructive operation ---------------------------------------

def test_delete_is_refused_under_authoring():
    """content.delete is separate from content.write on purpose: a credential that can
    create and update content must not thereby be able to destroy it."""
    with pytest.raises(ToolError) as e:
        build(profile="authoring")["delete_quizzes"](quiz_ids=["q1"])
    assert "content.delete" in str(e.value)


def test_delete_removes_the_quiz(quizzes):
    out = quizzes["delete_quizzes"](quiz_ids=["q1"])
    assert out["succeeded"] == 1
    with pytest.raises(ToolError):
        quizzes["get_quiz"](id="q1")


def test_delete_reports_an_unknown_id_per_item(quizzes):
    out = quizzes["delete_quizzes"](quiz_ids=["q1", "nope"])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "not_found"


def test_delete_is_annotated_destructive():
    client = SkilljarClient(PolicyBackend(FakeBackend(quizzes=list(QUIZZES)),
                                          Policy.from_profile("full")))
    app = MCPServer(name="t")
    register_quiz_tools(app, lambda: client)
    assert app._tool_manager._tools["delete_quizzes"].annotations.destructive_hint is True


def test_delete_requires_at_least_one_id(quizzes):
    with pytest.raises(ToolError) as e:
        quizzes["delete_quizzes"](quiz_ids=[])
    assert "at least one" in str(e.value)
