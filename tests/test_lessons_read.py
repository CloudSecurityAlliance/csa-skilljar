import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.lessons import register_lesson_tools
from csa_skilljar.policy import Policy, PolicyBackend

LESSONS = [
    {"type": "lessons", "id": "l1", "attributes": {
        "title": "Intro", "type": "HTML", "course_id": "c1", "order": 10,
        "content_html": "<p>hi</p>", "description_html": "",
        "modified_at": "2026-02-01T00:00:00Z"}},
    {"type": "lessons", "id": "l2", "attributes": {
        "title": "Quiz", "type": "QUIZ", "course_id": "c1", "order": 20, "quiz_id": "q1",
        "modified_at": "2026-03-01T00:00:00Z"}},
    {"type": "lessons", "id": "l3", "attributes": {
        "title": "Other", "type": "HTML", "course_id": "c2", "order": 10,
        "modified_at": "2026-01-01T00:00:00Z"}},
]


def tool(name, profile="parity"):
    client = SkilljarClient(PolicyBackend(FakeBackend(lessons=list(LESSONS)),
                                          Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_lesson_tools(app, lambda: client)
    return app._tool_manager._tools[name].fn


def test_list_lessons_returns_all_by_default():
    assert len(tool("list_lessons")()["lessons"]) == 3


def test_filter_course_id_narrows_to_one_course():
    out = tool("list_lessons")(filter_course_id="c1")
    assert {x["id"] for x in out["lessons"]} == {"l1", "l2"}


def test_filter_title_is_exact_unlike_list_courses():
    """The official server matches lesson titles EXACTLY and course titles partially."""
    assert tool("list_lessons")(filter_title="Intro")["lessons"][0]["id"] == "l1"
    assert tool("list_lessons")(filter_title="Intr")["lessons"] == []


def test_filter_type_is_exact():
    assert [x["id"] for x in tool("list_lessons")(filter_type="QUIZ")["lessons"]] == ["l2"]


def test_an_unknown_filter_type_is_rejected_locally_not_sent():
    """The official server 422s on an unknown value. Rejecting locally gives the model
    the valid set in the message instead of an opaque upstream error."""
    with pytest.raises(ToolError) as e:
        tool("list_lessons")(filter_type="PODCAST")
    assert "PODCAST" in str(e.value)
    assert "HTML" in str(e.value), "the error must list the values that ARE valid"


def test_filter_updated_since_narrows_by_timestamp():
    out = tool("list_lessons")(filter_updated_since="2026-02-15T00:00:00Z")
    assert [x["id"] for x in out["lessons"]] == ["l2"]


def test_official_argument_names_are_reproduced_exactly():
    params = set(inspect.signature(tool("list_lessons")).parameters)
    for official in ("filter_course_id", "filter_title", "filter_type", "filter_updated_since"):
        assert official in params, f"ADR-006: {official} must match the official server"


def test_pagination_is_our_additive_extension():
    params = set(inspect.signature(tool("list_lessons")).parameters)
    assert {"page_cursor", "page_size"} <= params
    out = tool("list_lessons")(page_size=2)
    assert len(out["lessons"]) == 2
    assert out["has_more"] is True


def test_the_listing_does_not_carry_lesson_bodies():
    """Deliberate: a listing of every lesson body is large and rarely wanted."""
    assert "content_html" not in tool("list_lessons")()["lessons"][0]


def test_get_lesson_returns_detail_including_content():
    out = tool("get_lesson")(id="l1")
    assert out["id"] == "l1"
    assert out["content_html"] == "<p>hi</p>"
    assert out["type"] == "HTML"


def test_get_lesson_unknown_id_is_readable():
    with pytest.raises(ToolError) as e:
        tool("get_lesson")(id="nope")
    assert "nope" in str(e.value)


def test_bad_page_size_is_rejected():
    with pytest.raises(ToolError) as e:
        tool("list_lessons")(page_size=0)
    assert "page_size" in str(e.value)
