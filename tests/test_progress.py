"""The learner-progress tools, and the ADR-002 routing rule they are the first test of."""
import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar import policy as P
from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.progress import register_progress_tools
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

from .test_v1backend import PROGRESS, USERS


def build(profile="parity", with_v1=True):
    policy = Policy.from_profile(profile)
    v1 = PolicyBackend(FakeV1Backend(users=USERS, progress=PROGRESS), policy) \
        if with_v1 else None
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy), v1=v1)
    app = MCPServer(name="t")
    register_progress_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- the v1-only fields, which is the whole justification -----------------------------

def test_progress_carries_the_lesson_counts_v2_cannot_answer(tools):
    """ADR-002: v1 earns a tool only where v2 lacks the capability. v2's enrolment
    record has no lesson counts, so "40% of the way through" is answerable only here."""
    row = tools["list_learner_progress"](user_id="u1")["progress"][0]
    assert row["completed_lesson_count"] == 4
    assert row["lesson_count"] == 10
    assert row["completed_required_lesson_count"] == 3
    assert row["required_lesson_count"] == 8
    assert row["credits_earned"] == "2"
    assert row["credit_unit_plural"] == "CPEs"


def test_v2_really_does_lack_these_fields():
    """Guards the justification itself. If v2 ever grows lesson counts, ADR-002 says
    this capability moves to v2 and this tool retires - so the claim must be checked,
    not assumed."""
    import json
    import pathlib
    spec = json.loads((pathlib.Path(__file__).resolve().parent.parent
                       / "specs" / "skilljar-v2-openapi.json").read_text())
    v2_enrolment = set(spec["components"]["schemas"]["EnrollmentAttributes"]["properties"])
    for field in ("completed_lesson_count", "completed_required_lesson_count",
                  "credits_earned", "lesson_count"):
        assert field not in v2_enrolment, (
            f"v2 now carries {field}; ADR-002 means this capability moves to v2")


def test_a_re_enrolment_is_visible():
    """A low progress figure next to a silent re-enrolment reads as lost work rather
    than a fresh attempt."""
    row = build()["list_learner_progress"](user_id="u1")["progress"][0]
    assert row["enrollment_count"] == 2


# --- trap 6: per-lesson progress does not exist ---------------------------------------

def test_no_tool_claims_per_lesson_progress(tools):
    """Skilljar's v1 document describes `/v1/users/{id}/published-courses/{id}/lessons`.
    It returns 404 on the live API. A tool built from the spec would fail forever, and a
    model must not report the counts as per-lesson detail."""
    for name in ("list_learner_progress", "get_learner_progress"):
        doc = inspect.getdoc(tools[name]) or ""
        assert "COUNTS ONLY, NOT WHICH LESSONS" in doc
    assert "404" in (inspect.getdoc(tools["list_learner_progress"]) or "")
    out = tools["list_learner_progress"](user_id="u1")
    assert "not WHICH ones" in out["note"]


# --- the by-id trap -------------------------------------------------------------------

def test_each_publication_returns_its_own_record(tools):
    """The fixture publishes one course to two domains, which is what made Skilljar's
    own by-id endpoint return the wrong one."""
    a = tools["get_learner_progress"](user_id="u1", published_course_id="pc1")
    b = tools["get_learner_progress"](user_id="u1", published_course_id="pc2")
    assert a["domain_name"] == "learn.example.org"
    assert b["domain_name"] == "training.example.org"
    assert a["course_id"] == b["course_id"] == "c1"      # same course, two publications


def test_get_explains_that_a_course_can_have_two_publications(tools):
    doc = inspect.getdoc(tools["get_learner_progress"]) or ""
    assert "ON A PARTICULAR DOMAIN" in doc
    assert "resolves by the underlying course" in doc.lower()


# --- learner lookup -------------------------------------------------------------------

def test_find_learner_unnests_the_user(tools):
    row = tools["find_learner"](email="ada@example.org")["learners"][0]
    assert row["id"] == "u1"
    assert row["email"] == "ada@example.org"
    assert row["registration_count"] == 3


def test_find_learner_surfaces_v1s_total(tools):
    """v1 gives a count; v2 never does. It is the only way to say "3 of 4,278"."""
    assert tools["find_learner"](email="ada@example.org")["total"] == 1


def test_an_unknown_email_is_empty_not_an_error(tools):
    out = tools["find_learner"](email="nobody@example.org")
    assert out["learners"] == []
    assert "not a bad address" in out["note"]


# --- no v1 credential ------------------------------------------------------------------

def test_without_a_v1_key_the_error_names_the_variable_and_says_it_is_separate():
    """The likeliest confusion is thinking the v2 client covers this."""
    tools = build(with_v1=False)
    with pytest.raises(ToolError) as e:
        tools["list_learner_progress"](user_id="u1")
    assert "CSA_SKILLJAR_V1_API_KEY" in str(e.value)
    assert "separate credential" in str(e.value)


def test_the_v2_surface_still_works_without_a_v1_key():
    """A v1 key is not needed for any of v2. Requiring one would make the whole server
    depend on a credential most installs do not have."""
    client = SkilljarClient(PolicyBackend(FakeBackend(courses=[]),
                                          Policy.from_profile("parity")), v1=None)
    assert client.list_courses()["data"] == []


# --- ADR-002: exactly one backend owns each capability ---------------------------------

def test_no_capability_is_served_by_both_backends():
    """The rule this block is the first real test of. A capability answered by both
    would return a JSON:API shape or a DRF shape depending on which backend happened to
    reply - the silent degradation ADR-002 exists to prevent."""
    from csa_skilljar.backend import Backend
    from csa_skilljar.v1backend import V1Backend

    v2_methods = {n for n in dir(Backend) if not n.startswith("_")}
    v1_methods = {n for n in dir(V1Backend)
                  if not n.startswith("_") and callable(getattr(V1Backend, n))}
    overlap = sorted(v2_methods & v1_methods)
    assert not overlap, f"served by BOTH backends, which ADR-002 forbids: {overlap}"


def test_every_v1_method_is_gated_by_the_same_table():
    """One `_GATES` table covers both APIs. A capability gated in one and open in the
    other would be a hole invisible from either backend alone."""
    from csa_skilljar.v1backend import V1Backend
    v1_methods = {n for n in dir(V1Backend)
                  if not n.startswith("_") and callable(getattr(V1Backend, n))}
    ungated = sorted(v1_methods - set(P._GATES))
    assert not ungated, f"v1 methods with no declared gate: {ungated}"


def test_progress_is_refused_without_the_capability():
    tools = build(profile="authoring")     # no progress.read
    with pytest.raises(ToolError) as e:
        tools["list_learner_progress"](user_id="u1")
    assert "progress.read" in str(e.value)
