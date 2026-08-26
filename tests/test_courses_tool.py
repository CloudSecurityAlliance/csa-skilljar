import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.courses import register_course_tools
from csa_skilljar.policy import Policy, PolicyBackend

ROWS = [{"type": "courses", "id": "c1",
         "attributes": {"title": "Zero Trust", "external_id": "zt",
                        "is_published": True, "lesson_count": 4}}]


def build(courses, profile="parity"):
    client = SkilljarClient(PolicyBackend(FakeBackend(courses=courses), Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_course_tools(app, lambda: client)
    return app._tool_manager._tools["list_courses"].fn


def test_flattens_the_jsonapi_envelope():
    out = build(ROWS)()
    assert out["courses"][0] == {"id": "c1", "title": "Zero Trust", "external_id": "zt",
                                 "is_published": True, "lesson_count": 4}
    assert out["has_more"] is False


def test_filter_title_matches_the_official_argument_name():
    """ADR-006: identical tool and argument names to the official server."""
    assert "filter_title" in inspect.signature(build(ROWS)).parameters


def test_pagination_is_our_additive_extension():
    rows = [{"type": "courses", "id": f"c{i}", "attributes": {"title": str(i)}} for i in range(5)]
    out = build(rows)(page_size=2)
    assert len(out["courses"]) == 2
    assert out["has_more"] is True
    assert out["next_cursor"] == "2"


def test_omitting_pagination_matches_the_official_behaviour():
    """A caller sending exactly what the official server accepts gets what it returns."""
    rows = [{"type": "courses", "id": f"c{i}", "attributes": {"title": str(i)}} for i in range(3)]
    assert len(build(rows)(filter_title="1")["courses"]) == 1


def test_note_warns_that_results_may_be_a_page():
    assert "page" in build(ROWS)()["note"].lower()


def test_bad_page_size_is_a_readable_error():
    with pytest.raises(ToolError) as e:
        build(ROWS)(page_size=0)
    assert "page_size" in str(e.value)


def test_disabled_capability_surfaces_as_a_readable_toolerror():
    with pytest.raises(ToolError) as e:
        build(ROWS, profile="admin")()
    assert "content.read" in str(e.value)
    assert "CSA_SKILLJAR_PROFILE" in str(e.value)
