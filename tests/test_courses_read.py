import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.courses import register_course_tools
from csa_skilljar.policy import Policy, PolicyBackend

ROW = {"type": "courses", "id": "c1", "attributes": {
    "title": "Zero Trust", "short_description": "ZT basics",
    "long_description_html": "<p>ZT</p>", "enforce_sequential_navigation": True,
    "is_published": True, "lesson_count": 4, "external_id": "zt",
    "created_at": "2026-01-01T00:00:00Z", "modified_at": "2026-02-01T00:00:00Z"}}


def tool(name, courses=(ROW,), profile="parity"):
    client = SkilljarClient(PolicyBackend(FakeBackend(courses=list(courses)),
                                          Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_course_tools(app, lambda: client)
    return app._tool_manager._tools[name].fn


def test_get_course_returns_the_flattened_detail():
    out = tool("get_course")(id="c1")
    assert out["id"] == "c1"
    assert out["title"] == "Zero Trust"
    assert out["enforce_sequential_navigation"] is True
    assert out["lesson_count"] == 4


def test_get_course_returns_more_than_the_listing_does():
    """The reason this tool exists alongside list_courses."""
    detailed = set(tool("get_course")(id="c1"))
    listed = set(tool("list_courses")()["courses"][0])
    assert detailed > listed


def test_get_course_on_an_unknown_id_is_a_readable_not_found():
    with pytest.raises(ToolError) as e:
        tool("get_course")(id="nope")
    assert "nope" in str(e.value)


def test_get_course_argument_is_named_id_matching_the_official_server():
    assert list(inspect.signature(tool("get_course")).parameters) == ["id"]


def test_get_course_is_refused_when_the_capability_is_off():
    with pytest.raises(ToolError) as e:
        tool("get_course", profile="admin")(id="c1")
    assert "content.read" in str(e.value)
