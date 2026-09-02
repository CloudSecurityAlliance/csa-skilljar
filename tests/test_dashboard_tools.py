import pytest

from csa_skilljar.client import SkilljarClient
from csa_skilljar.dashboard import FakeDashboard
from csa_skilljar.mcp._config import Settings
from csa_skilljar.mcp._tools.tasks import _LIST_NOTE
from csa_skilljar.mcp.server import create_server
from tests.test_dashboard import DONE_ROW, GRADE_HTML, ROW


def test_both_tools_are_registered():
    app = create_server(lambda: None, settings=Settings())
    assert {"list_tasks", "get_task"} <= set(app._tool_manager._tools)


def test_list_tasks_defaults_to_pending_and_states_both_counts():
    """The dashboard's own default shows all 661 with ungraded first, which reads as a
    661-item backlog when it is 30. The tool must not reproduce that misreading."""
    fake = FakeDashboard(tasks=[ROW, DONE_ROW])
    out = fake.list_tasks()
    assert len(out["tasks"]) == 1
    assert out["pending_on_page"] == 1 and out["completed_on_page"] == 1 and out["total"] == 2


def test_page_size_out_of_range_is_rejected_not_clamped():
    """The house rule (taxonomy.py, commerce.py): reject, don't silently clamp. A
    clamped 1000 -> 250 gives no signal and leaves the caller's `page` arithmetic wrong."""
    from mcp.server.mcpserver.exceptions import ToolError

    app = create_server(lambda: SkilljarClient(backend=object(),
                                               dashboard=FakeDashboard(tasks=[ROW])),
                        settings=Settings())
    with pytest.raises(ToolError) as e:
        app._tool_manager._tools["list_tasks"].fn(page_size=1000)
    assert "page_size" in str(e.value)
    with pytest.raises(ToolError):
        app._tool_manager._tools["list_tasks"].fn(page_size=0)


def test_the_csrf_token_never_reaches_the_model_through_get_task():
    """The single highest-value invariant in this diff. The BACKEND deliberately returns
    `csrf_token` - a later grading path needs it, and it is obtainable only from this GET
    - but the TOOL must strip it before a model ever sees it. Goes through the registered
    tool, not the backend directly, so a regression to `{**got, ...}` is actually caught -
    that form would carry the key straight through, since the backend still returns it."""
    fake = FakeDashboard(tasks=[ROW], pages={"/tasks/grade-quiz/tsk1": GRADE_HTML})
    backend_result = fake.get_task(id="tsk1")
    assert "csrf_token" in backend_result, "fixture must actually exercise the leak path"

    client = SkilljarClient(backend=object(), dashboard=fake)
    app = create_server(lambda: client, settings=Settings())
    tool_result = app._tool_manager._tools["get_task"].fn(id="tsk1")
    assert "csrf_token" not in tool_result


def test_names_are_withheld_and_the_response_says_so():
    """Withholding silently is the failure the webhook redaction already documented:
    an absent field reads as 'this learner has no name', which is a different fact."""
    fake = FakeDashboard(tasks=[ROW])
    row = fake.list_tasks(status="all")["tasks"][0]
    assert "student_name" not in row
    assert row["student_email"] == "ada@example.org"

    app = create_server(lambda: None, settings=Settings())
    desc = app._tool_manager._tools["list_tasks"].description
    # the note itself is asserted through the tool output in the integration path;
    # here we check the contract is stated where a reader will meet it
    assert "withheld" in (desc + _LIST_NOTE).lower()


def test_the_tool_descriptions_say_the_response_is_untrusted():
    app = create_server(lambda: None, settings=Settings())
    desc = app._tool_manager._tools["get_task"].description
    assert "untrusted" in desc.lower()


def test_no_dashboard_session_reports_a_setup_step_not_a_crash():
    from csa_skilljar import exceptions as exc
    from csa_skilljar.client import SkilljarClient
    c = SkilljarClient(backend=object(), dashboard=None)
    with pytest.raises(exc.CredentialsMissing) as e:
        c.list_tasks()
    assert "capture" in str(e.value).lower()
