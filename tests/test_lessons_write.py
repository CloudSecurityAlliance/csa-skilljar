import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.lessons import register_lesson_tools
from csa_skilljar.policy import Policy, PolicyBackend


@pytest.fixture
def lessons():
    client = SkilljarClient(PolicyBackend(FakeBackend(), Policy.from_profile("full")))
    app = MCPServer(name="t")
    register_lesson_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


HTML = {"course_id": "c1", "type": "HTML", "title": "T", "content_html": "<p>x</p>"}
MODULAR = {"course_id": "c1", "type": "MODULAR", "title": "T",
           "content_items": [{"type": "HTML", "content_html": "<p>a</p>"}]}
QUIZ = {"course_id": "c1", "type": "QUIZ", "title": "T", "quiz_id": "q1"}


# --- create: the XOR rules -------------------------------------------------------

@pytest.mark.parametrize("attrs,missing", [
    ({"course_id": "c1", "type": "HTML", "title": "T"}, "content_html"),
    ({"course_id": "c1", "type": "MODULAR", "title": "T"}, "content_items"),
    ({"course_id": "c1", "type": "QUIZ", "title": "T"}, "quiz_id"),
])
def test_each_type_requires_its_own_content_field(lessons, attrs, missing):
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[attrs])
    assert missing in str(e.value)


@pytest.mark.parametrize("attrs,forbidden", [
    ({**HTML, "quiz_id": "q1"}, "quiz_id"),
    ({**QUIZ, "content_html": "<p>x</p>"}, "content_html"),
    ({**MODULAR, "content_html": "<p>x</p>"}, "content_html"),
])
def test_each_type_forbids_the_others_content_field(lessons, attrs, forbidden):
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[attrs])
    assert forbidden in str(e.value)


def test_only_three_types_are_creatable(lessons):
    """list_lessons filters over eight types; only three can be created."""
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[{"course_id": "c1", "type": "ASSET", "title": "T"}])
    msg = str(e.value)
    assert "HTML" in msg and "MODULAR" in msg and "QUIZ" in msg


def test_html_content_must_be_non_empty(lessons):
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[{**HTML, "content_html": ""}])
    assert "content_html" in str(e.value)


def test_content_items_are_capped_at_fifteen(lessons):
    items = [{"type": "HTML", "content_html": "<p>x</p>"} for _ in range(16)]
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[{**MODULAR, "content_items": items}])
    assert "15" in str(e.value)


def test_at_most_one_quiz_and_one_rating_among_content_items(lessons):
    two_quizzes = [{"type": "QUIZ", "quiz_id": "q1"}, {"type": "QUIZ", "quiz_id": "q2"}]
    with pytest.raises(ToolError) as e:
        lessons["create_lessons"](lessons=[{**MODULAR, "content_items": two_quizzes}])
    assert "QUIZ" in str(e.value)


def test_a_valid_lesson_of_each_type_is_created(lessons):
    out = lessons["create_lessons"](lessons=[HTML, MODULAR, QUIZ])
    assert out["succeeded"] == 3
    assert out["failed"] == []


def test_course_id_and_title_are_required(lessons):
    for attrs, missing in (({"type": "HTML", "title": "T", "content_html": "<p>x</p>"}, "course_id"),
                           ({"course_id": "c1", "type": "HTML", "content_html": "<p>x</p>"}, "title")):
        with pytest.raises(ToolError) as e:
            lessons["create_lessons"](lessons=[attrs])
        assert missing in str(e.value)


# --- update: the tri-state -------------------------------------------------------

def test_omitting_content_items_leaves_children_untouched(lessons):
    lid = lessons["create_lessons"](lessons=[MODULAR])["ids"][0]
    lessons["update_lessons"](lessons=[{"id": lid, "title": "Renamed"}])
    got = lessons["get_lesson"](id=lid)
    assert got["title"] == "Renamed"
    assert len(got["content_items"]) == 1


def test_a_non_empty_content_items_list_replaces_the_children(lessons):
    lid = lessons["create_lessons"](lessons=[MODULAR])["ids"][0]
    lessons["update_lessons"](lessons=[{"id": lid, "content_items": [
        {"type": "HTML", "content_html": "<p>b</p>"},
        {"type": "HTML", "content_html": "<p>c</p>"}]}])
    assert len(lessons["get_lesson"](id=lid)["content_items"]) == 2


def test_an_empty_content_items_list_requires_explicit_confirmation(lessons):
    """An empty list is what a caller produces when a loop found nothing. Requiring a
    flag means an accident cannot delete every child of a lesson."""
    lid = lessons["create_lessons"](lessons=[MODULAR])["ids"][0]
    with pytest.raises(ToolError) as e:
        lessons["update_lessons"](lessons=[{"id": lid, "content_items": []}])
    msg = str(e.value)
    assert "delete every content item" in msg.lower()
    assert "confirm_delete_all_content_items" in msg
    assert len(lessons["get_lesson"](id=lid)["content_items"]) == 1, "nothing deleted"


def test_the_confirmation_flag_permits_the_deletion(lessons):
    lid = lessons["create_lessons"](lessons=[MODULAR])["ids"][0]
    out = lessons["update_lessons"](lessons=[{"id": lid, "content_items": []}],
                                    confirm_delete_all_content_items=True)
    assert out["succeeded"] == 1
    assert lessons["get_lesson"](id=lid)["content_items"] == []


def test_lesson_type_is_rejected_rather_than_silently_ignored(lessons):
    """ADR-008. The official server accepts `type` on update and SILENTLY IGNORES it.
    A caller who thinks they changed the type and did not is worse off than one who
    got an error."""
    lid = lessons["create_lessons"](lessons=[HTML])["ids"][0]
    with pytest.raises(ToolError) as e:
        lessons["update_lessons"](lessons=[{"id": lid, "type": "QUIZ"}])
    assert "read-only" in str(e.value).lower()


def test_update_requires_an_id(lessons):
    with pytest.raises(ToolError) as e:
        lessons["update_lessons"](lessons=[{"title": "New"}])
    assert "id" in str(e.value)


def test_an_unknown_id_is_a_per_item_failure(lessons):
    out = lessons["update_lessons"](lessons=[{"id": "nope", "title": "X"}])
    assert out["succeeded"] == 0
    assert out["failed"][0]["code"] == "not_found"
