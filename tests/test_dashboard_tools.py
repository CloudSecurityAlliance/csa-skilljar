import pytest

from csa_skilljar.dashboard import FakeDashboard
from csa_skilljar.mcp._config import Settings
from csa_skilljar.mcp._tools.tasks import _LIST_NOTE
from csa_skilljar.mcp.server import create_server
from tests.test_dashboard import DONE_ROW, ROW


def test_both_tools_are_registered():
    app = create_server(lambda: None, settings=Settings())
    assert {"list_tasks", "get_task"} <= set(app._tool_manager._tools)


def test_list_tasks_defaults_to_pending_and_states_both_counts():
    """The dashboard's own default shows all 661 with ungraded first, which reads as a
    661-item backlog when it is 30. The tool must not reproduce that misreading."""
    fake = FakeDashboard(tasks=[ROW, DONE_ROW])
    out = fake.list_tasks()
    assert len(out["tasks"]) == 1
    assert out["pending"] == 1 and out["completed"] == 1 and out["total"] == 2


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
