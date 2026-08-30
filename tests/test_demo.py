"""The demonstration plan — and the coverage number that makes a clean run mean something.

Per the CINO pattern: the plan is data, coverage is computed from the registry, and a
tool added next block must appear as a HOLE rather than be quietly absent.
"""
import inspect

import pytest

from csa_skilljar import policy as P
from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp._tools.demo import DEMO_ACCOUNTS, EXCLUDED
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend


def server(profile="full"):
    pol = Policy.from_profile(profile)
    client = SkilljarClient(PolicyBackend(FakeBackend(), pol),
                            v1=PolicyBackend(FakeV1Backend(), pol))
    return create_server(lambda: client, settings=settings_from_env({}))


def plan(mode="read_only", profile="full"):
    app = server(profile)
    return app, app._tool_manager._tools["demonstration_plan"].fn(mode=mode)


# --- coverage is computed, and reaches zero -------------------------------------------

@pytest.mark.parametrize("mode", ["read_only", "read_write"])
def test_every_tool_is_accounted_for(mode):
    """THE test. Every registered tool must be exercised, excluded with a reason, or
    out-of-scope for the mode - so a tool added next block lands in `not_exercised` and
    is visible rather than quietly missing."""
    app, p = plan(mode)
    assert p["coverage"]["not_exercised"] == [], (
        "these tools are in no plan and have no exclusion reason - add a step, or add "
        f"them to EXCLUDED with why: {p['coverage']['not_exercised']}")


def test_the_coverage_number_is_computed_not_asserted():
    """A maintained list would drift. This reads the live registry, so the count moves
    when the server does."""
    app, p = plan()
    assert p["coverage"]["registered"] == len(app._tool_manager._tools)


def test_a_newly_added_tool_shows_up_as_a_gap():
    """Guards the guard: if coverage stopped being computed from the registry, every
    other assertion here would keep passing while covering less and less."""
    app = server()

    @app.tool()
    def a_tool_added_next_block() -> dict:
        """Invented by this test to prove an unplanned tool is visible."""
        return {}

    p = app._tool_manager._tools["demonstration_plan"].fn(mode="read_write")
    assert "a_tool_added_next_block" in p["coverage"]["not_exercised"]


def test_the_exclusion_list_is_pairs_not_a_dict_literal():
    """Bandit reads a dict key containing "password", "secret" or "token" mapped to a
    string as a hardcoded credential, and flagged four of these prose reasons. The pairs
    form removes the finding honestly; a dict literal would bring it back, and four
    scanner suppressions would only hide it."""
    from csa_skilljar.mcp._tools import demo
    assert isinstance(demo._EXCLUSIONS, tuple)
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in demo._EXCLUSIONS)
    assert len(demo._EXCLUSIONS) == len(demo.EXCLUDED), "a duplicate key would silently drop one"


def test_every_exclusion_carries_a_reason():
    """An exclusion nobody can read is how a coverage number gets gamed."""
    for tool, reason in EXCLUDED.items():
        assert len(reason) > 20, f"{tool}'s exclusion reason is too thin to review"


def test_exclusions_name_real_tools():
    """A typo in EXCLUDED would silently stop excluding, and the tool would reappear as
    an unexplained gap - or worse, be planned."""
    registered = set(server()._tool_manager._tools)
    unknown = sorted(set(EXCLUDED) - registered)
    assert not unknown, f"EXCLUDED names tools that do not exist: {unknown}"


def test_out_of_scope_is_separate_from_uncovered():
    """In read_only a write tool is out of scope, not a gap. Conflating them means the
    gap count never reaches zero, so nobody ever looks at it."""
    _, ro = plan("read_only")
    _, rw = plan("read_write")
    assert ro["coverage"]["out_of_scope_for_this_mode"], "writes should be out of scope"
    assert rw["coverage"]["out_of_scope_for_this_mode"] == []
    assert "create_courses" in ro["coverage"]["out_of_scope_for_this_mode"]


# --- the plan is a plan, not a result ---------------------------------------------------

def test_it_returns_steps_rather_than_running_them():
    """Running everything here would block a conversation behind one call and the model
    would have demonstrated nothing - the tool would have done the work."""
    _, p = plan()
    assert p["steps"] and all("tool" in s and "narrate" in s for s in p["steps"])
    doc = inspect.getdoc(
        server()._tool_manager._tools["demonstration_plan"].fn) or ""
    assert "it does not run them" in doc


def test_steps_chain_by_referring_to_earlier_output():
    """The model has to carry ids forward, which is what tests whether the descriptions
    are usable from a standing start."""
    _, p = plan()
    assert any("<id from" in str(s["arguments"]) for s in p["steps"])


# --- the two modes -----------------------------------------------------------------------

def test_read_only_contains_no_write_step():
    _, p = plan("read_only")
    assert not any(s.get("writes") for s in p["steps"])
    assert "READ-ONLY" in p["safety"]


def test_read_write_marks_its_write_steps_and_warns():
    _, p = plan("read_write")
    writes = [s for s in p["steps"] if s.get("writes")]
    assert writes
    assert "REAL DATA" in p["safety"]
    assert "NO WRITE TOOL IN THIS PROJECT HAS EVER BEEN RUN" in p["safety"]


def test_read_write_says_the_course_cannot_be_cleaned_up_BEFORE_creating_it():
    """There is no delete_courses tool anywhere. Saying so afterwards is too late, and
    the first use of this pattern elsewhere left seven real files behind."""
    _, p = plan("read_write")
    assert "NO delete_courses TOOL" in p["cleanup_warning"]
    assert "BEFORE creating it" in p["cleanup_warning"]


def test_every_write_step_has_a_cleanup_or_says_why_not():
    _, p = plan("read_write")
    for s in p["steps"]:
        if not s.get("writes"):
            continue
        # Either it cleans up, or a later step does, or the warning covers it.
        assert s.get("cleanup_with") or s["tool"].startswith(
            ("update_", "delete_", "unbind_")), f"{s['tool']} writes with no cleanup path"


def test_an_unknown_mode_is_refused():
    from mcp.server.mcpserver.exceptions import ToolError
    app = server()
    # translate_errors turns a ValueError into a ToolError, which is the contract that
    # keeps the message from being discarded (CLAUDE.md invariant 2).
    with pytest.raises(ToolError) as e:
        app._tool_manager._tools["demonstration_plan"].fn(mode="destroy_everything")
    assert "read_only" in str(e.value)


# --- refusals are predicted up front -------------------------------------------------------

def test_refusals_are_predicted_for_the_actual_profile():
    """So a narrator can say what will be skipped instead of walking into it one step at
    a time."""
    _, p = plan(profile="parity")
    refused = {r["tool"] for r in p["will_be_refused"]}
    assert refused, "parity cannot reach commerce or events; that should be predicted"
    assert "before_you_start" in p
    for r in p["will_be_refused"]:
        assert r["needs"] in P.ALL_CAPABILITIES


def test_a_missing_oauth_scope_is_predicted_too():
    """The first live run predicted ZERO refusals and then hit two: the capability
    profile allowed the call and the SCOPE pre-check stopped it. Predicting one kind and
    not the other is a prediction that walks you into the other."""
    class Creds:
        def granted_scopes(self):
            return ("courses:read",)          # everything else is missing

    class Client(SkilljarClient):
        @property
        def credentials(self):
            return Creds()

    pol = Policy.from_profile("full")
    client = Client(PolicyBackend(FakeBackend(), pol),
                    v1=PolicyBackend(FakeV1Backend(), pol))
    app = create_server(lambda: client, settings=settings_from_env({}))
    p = app._tool_manager._tools["demonstration_plan"].fn()

    by_scope = [r for r in p["will_be_refused"]
                if r["refused_by"] == "OAuth scope on the v2 credential"]
    assert by_scope, "a credential holding only courses:read must refuse most steps"
    assert {r["tool"] for r in by_scope} >= {"list_students", "list_oauth_clients"}
    # A step the credential CAN do must not be predicted as refused.
    assert "list_courses" not in {r["tool"] for r in p["will_be_refused"]}


def test_every_predicted_refusal_says_which_control_refused_it():
    """A profile is changed with an environment variable and a restart; a scope needs the
    credential re-issued in the Dashboard. Saying only "refused" sends someone to the
    wrong remedy."""
    _, p = plan(profile="parity")
    for r in p["will_be_refused"]:
        assert r["refused_by"] in ("capability profile",
                                   "OAuth scope on the v2 credential")


def test_a_full_profile_predicts_no_refusals():
    """With no credential to read scopes from, only the capability check applies - and
    `full` grants everything."""
    _, p = plan(profile="full")
    assert p["will_be_refused"] == []
    assert "before_you_start" not in p


# --- PII discipline --------------------------------------------------------------------------

def test_learner_steps_use_named_accounts_only():
    """DATA-RESOURCES.md: a transcript persists, the org holds tens of thousands of real
    learners, and Skilljar cannot filter by domain - so the plan must START from named
    addresses rather than narrow a listing."""
    _, p = plan()
    text = str(p["steps"])
    assert any(a in text for a in DEMO_ACCOUNTS)
    # An unfiltered learner listing must not appear anywhere in the plan.
    for step in p["steps"]:
        if step["tool"] in ("list_students", "list_learner_progress",
                            "list_signup_field_values", "list_vilt_registrations"):
            assert step["arguments"], f"{step['tool']} is listed with no filter"


def test_the_registration_step_is_filtered_to_one_session():
    _, p = plan()
    step = next(s for s in p["steps"] if s["tool"] == "list_vilt_registrations")
    assert "filter_session_id" in step["arguments"]


def test_the_asset_step_warns_about_the_download_url():
    _, p = plan()
    step = next(s for s in p["steps"] if s["tool"] == "get_asset")
    assert "do NOT paste the URL" in step["look_for"]


# --- honest reporting ---------------------------------------------------------------------------

def test_it_asks_for_two_facts_not_one():
    """A run that exercised nothing also produced no errors (ZD-17)."""
    _, p = plan()
    assert "TWO separate facts" in p["how_to_report"]
    assert "exercised nothing also produced no errors" in p["how_to_report"]


def test_it_states_its_own_limits():
    """A live run exercises the happy path and one configured posture. Saying so stops
    the report overstating itself."""
    _, p = plan()
    joined = " ".join(p["honest_limits"]).lower()
    assert "happy path" in joined
    assert "same gate" in joined
    assert "ambiguous" in joined


def test_the_read_only_run_ends_by_inviting_feedback():
    _, p = plan("read_only")
    assert "report_a_problem" in p["at_the_end"]


def test_the_read_write_run_ends_by_checking_cleanup_actually_ran():
    """The best bug the original pattern found was a cleanup step that narrated cleanup
    without doing it."""
    _, p = plan("read_write")
    assert "Confirm every cleanup step ran" in p["at_the_end"]
