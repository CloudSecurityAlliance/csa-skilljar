import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.courses import register_course_tools
from csa_skilljar.policy import Policy, PolicyBackend


@pytest.fixture
def courses():
    """One client shared by every course tool - create/read/update over one backend is
    the realistic shape, and a fresh client per call cannot test round trips."""
    client = SkilljarClient(PolicyBackend(FakeBackend(), Policy.from_profile("full")))
    app = MCPServer(name="t")
    register_course_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


def read_only():
    client = SkilljarClient(PolicyBackend(FakeBackend(), Policy.from_profile("parity")))
    app = MCPServer(name="t")
    register_course_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


# --- create --------------------------------------------------------------------

def test_creating_two_courses_reports_both(courses):
    out = courses["create_courses"](courses=[{"title": "One"}, {"title": "Two"}])
    assert out["total"] == 2
    assert out["succeeded"] == 2
    assert out["failed"] == []
    assert len(out["ids"]) == 2


def test_a_partial_failure_is_reported_per_item_not_collapsed(courses):
    """The whole reason the 207 envelope exists. A caller told only 'the batch failed'
    cannot tell which rows landed.

    Uses a SERVICE-level failure (an unresolvable created_by_email), not a schema one.
    A schema violation rejects the entire request upstream, so it can never produce a
    partial result - see test_a_local_rejection_writes_nothing."""
    out = courses["create_courses"](courses=[
        {"title": "Fine"},
        {"title": "Orphan", "created_by_email": "nobody@example.org"}])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "not_found"
    assert out["failed"][0]["pointer"].startswith("/data/1")
    titles = [c["title"] for c in courses["list_courses"]()["courses"]]
    assert titles == ["Fine"], "the good row landed and the bad one did not"


def test_an_empty_list_is_rejected_before_any_call(courses):
    with pytest.raises(ToolError) as e:
        courses["create_courses"](courses=[])
    assert "at least one" in str(e.value)


def test_a_missing_title_names_which_item_was_wrong(courses):
    with pytest.raises(ToolError) as e:
        courses["create_courses"](courses=[{"title": "ok"}, {"short_description": "no title"}])
    assert "title" in str(e.value)
    assert "[1]" in str(e.value), "the error must identify WHICH item"


def test_an_unknown_attribute_is_rejected_rather_than_silently_dropped(courses):
    with pytest.raises(ToolError) as e:
        courses["create_courses"](courses=[{"title": "X", "colour": "blue"}])
    assert "colour" in str(e.value)


def test_a_local_rejection_writes_nothing(courses):
    """Skilljar applies per-item isolation only AFTER the envelope parses: a schema
    violation on ONE item rejects the WHOLE request. Rejecting locally must behave the
    same way - no partial write - or we are more permissive than the API."""
    with pytest.raises(ToolError):
        courses["create_courses"](courses=[{"title": "Good"}, {"title": "X", "bogus": 1}])
    assert courses["list_courses"]()["courses"] == []


def test_write_is_refused_under_the_default_profile():
    with pytest.raises(ToolError) as e:
        read_only()["create_courses"](courses=[{"title": "X"}])
    assert "content.write" in str(e.value)


# --- update --------------------------------------------------------------------

def test_update_requires_an_id_per_item(courses):
    with pytest.raises(ToolError) as e:
        courses["update_courses"](courses=[{"title": "New"}])
    assert "id" in str(e.value)


def test_update_changes_only_what_is_supplied(courses):
    made = courses["create_courses"](courses=[{"title": "Old", "short_description": "keep"}])
    cid = made["ids"][0]
    out = courses["update_courses"](courses=[{"id": cid, "title": "New"}])
    assert out["succeeded"] == 1
    got = courses["get_course"](id=cid)
    assert got["title"] == "New"
    assert got["short_description"] == "keep", "an omitted field must be preserved"


def test_updating_an_unknown_id_is_a_per_item_failure_not_a_batch_error(courses):
    """Skilljar reports a bad id per item inside a 207, never as a document-level error."""
    out = courses["update_courses"](courses=[{"id": "nope", "title": "X"}])
    assert out["succeeded"] == 0
    assert out["failed"][0]["code"] == "not_found"


def test_update_rejects_an_unknown_attribute(courses):
    made = courses["create_courses"](courses=[{"title": "T"}])
    with pytest.raises(ToolError) as e:
        courses["update_courses"](courses=[{"id": made["ids"][0], "colour": "red"}])
    assert "colour" in str(e.value)
