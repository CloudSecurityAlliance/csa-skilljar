"""Every paginated tool must actually paginate.

Five tools shipped reading `has_more` and `next_cursor` out of `meta`. Real Skilljar -
and `FakeBackend`, which matches it - put both at the TOP LEVEL of the envelope, and
`meta` carries only `page_size`. So those five always reported `has_more: false` and
never emitted a cursor: a caller was told "that is everything" when it was not.

Nothing caught it because the per-block tests asserted `has_more is False` on
single-page fixtures, which passes whether the code works or not. A test that can only
observe the value the bug produces is not a test of it.

This file is the guard: a fixture big enough to force a second page, driven through the
real tool, for every paginated tool at once - and FAIL-CLOSED, so a list tool added next
block is covered without anyone remembering.
"""
import inspect

import pytest

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend


def rows(kind, n, **attrs):
    return [{"type": kind, "id": f"{kind[:2]}{i}",
             "attributes": {"name": f"{kind} {i}", "title": f"{kind} {i}", **attrs}}
            for i in range(n)]


N = 7                       # enough that page_size=2 leaves more behind


def backend():
    """One fixture, deep enough in every collection to force a second page."""
    return FakeBackend(
        courses=rows("courses", N),
        lessons=[{"type": "lessons", "id": f"l{i}",
                  "attributes": {"title": f"L{i}", "course_id": "co0"}} for i in range(N)],
        quizzes=rows("quizzes", N),
        questions=[{"type": "questions", "id": f"qu{i}",
                    "attributes": {"quiz_id": "qu0", "question_html": "<p>?</p>",
                                   "question_type": "FREEFORM", "answers": []}}
                   for i in range(N)],
        question_banks=rows("question-banks", N),
        enrollments=[{"type": "enrollments", "id": f"e{i}", "attributes": {"active": True}}
                     for i in range(N)],
        certificates=[{"type": "certificates", "id": f"ce{i}", "attributes": {"status": "active"}}
                      for i in range(N)],
        students=[{"type": "students", "id": f"s{i}",
                   "attributes": {"email": f"s{i}@example.org"}} for i in range(N)],
        groups=[{"type": "groups", "id": f"g{i}",
                 "attributes": {"name": f"G{i}", "rule_email_domains": [],
                                "updated_at": "2026-01-01T00:00:00Z"}} for i in range(N)],
        signup_field_values=[{"type": "signup-field-values", "id": f"v{i}",
                              "attributes": {"label": "Job", "value": f"v{i}"},
                              "relationships": {
                                  "student": {"data": {"type": "students", "id": "s0"}},
                                  "signup-field": {"data": {"type": "signup-fields",
                                                            "id": "f0"}}}}
                             for i in range(N)],
        published_courses=[{"type": "published-courses", "id": f"pc{i}",
                            "attributes": {"slug": f"s{i}", "live": True},
                            "relationships": {
                                "course": {"data": {"type": "courses", "id": "co0"}},
                                "domain": {"data": {"type": "domains", "id": "d0"}}}}
                           for i in range(N)],
        domains=[{"type": "domains", "id": f"d{i}",
                  "attributes": {"name": f"d{i}.example", "access": "PUBLIC"}}
                 for i in range(N)],
        web_packages=rows("web-packages", N, state="READY"),
    )


def tools():
    fake = backend()
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile("full")))
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    # Visibility overrides have no constructor argument - they only exist once created,
    # so the fixture has to make them the same way a caller would.
    fns["add_visibility_overrides"](
        id="g0", overrides=[{"published_course_id": f"pc{i}"} for i in range(N)])
    return fns, fake


# The collection key each tool returns its rows under, and any argument it needs to
# reach a populated collection. A tool absent from here is caught by the coverage test.
PAGINATED = {
    "list_courses": ("courses", {}),
    "list_lessons": ("lessons", {}),
    "list_quizzes": ("quizzes", {}),
    "list_questions": ("questions", {}),
    "list_question_banks": ("question_banks", {}),
    "list_enrollments": ("enrollments", {}),
    "list_certificates": ("certificates", {}),
    "list_students": ("students", {}),
    "list_groups": ("groups", {}),
    "list_signup_field_values": ("values", {}),
    "list_published_courses": ("published_courses", {}),
    "list_domains": ("domains", {}),
    "list_visibility_overrides": ("overrides", {"id": "g0"}),
}

# Deliberately not paginated upstream, so they must NOT grow paging arguments.
NOT_PAGINATED = {"list_quiz_question_bank_assignments", "list_course_ratings",
                 "list_web_packages",
                 # Block 10. The client list is a small bounded set and the scope
                 # catalogue is served from in-memory constants; neither endpoint
                 # offers paging parameters.
                 "list_oauth_clients", "list_oauth_scopes"}


def test_every_list_tool_is_classified():
    """Fail-closed. A list tool added next block lands in neither set and fails here,
    rather than shipping unpaginated-and-untested like five of these did."""
    registered = {n for n in tools()[0] if n.startswith("list_")}
    unclassified = sorted(registered - set(PAGINATED) - NOT_PAGINATED)
    assert not unclassified, f"new list tools with no pagination verdict: {unclassified}"
    stale = sorted((set(PAGINATED) | NOT_PAGINATED) - registered)
    assert not stale, f"classified tools that no longer exist: {stale}"


@pytest.mark.parametrize("name", sorted(PAGINATED))
def test_a_first_page_reports_more_and_offers_a_cursor(name):
    """THE regression. Reading these from `meta` makes has_more always False and
    next_cursor never appear, and the caller stops after one page believing it has
    everything."""
    key, extra = PAGINATED[name]
    out = tools()[0][name](page_size=2, **extra)
    assert len(out[key]) == 2, f"{name} ignored page_size"
    assert out["has_more"] is True, (
        f"{name} says has_more=False with {N} rows and page_size=2 - it is probably "
        f"reading has_more out of `meta`, which carries only page_size")
    assert out.get("next_cursor"), f"{name} reports more but offers no cursor"


@pytest.mark.parametrize("name", sorted(PAGINATED))
def test_the_cursor_actually_advances(name):
    """A cursor that returns the same page is worse than none: the caller loops."""
    key, extra = PAGINATED[name]
    fns, _ = tools()
    first = fns[name](page_size=2, **extra)
    second = fns[name](page_size=2, page_cursor=first["next_cursor"], **extra)
    assert [r["id"] for r in second[key]] != [r["id"] for r in first[key]]


@pytest.mark.parametrize("name", sorted(PAGINATED))
def test_the_last_page_says_so(name):
    """The other half. A tool that always says has_more=True pages forever."""
    key, extra = PAGINATED[name]
    out = tools()[0][name](page_size=100, **extra)
    assert out["has_more"] is False
    assert "next_cursor" not in out
    assert len(out[key]) == N


@pytest.mark.parametrize("name", sorted(NOT_PAGINATED))
def test_unpaginated_tools_take_no_paging_arguments(name):
    """Upstream offers no paging for these. Accepting page_size would imply a control
    that does nothing, which is worse than not offering it."""
    params = set(inspect.signature(tools()[0][name]).parameters)
    assert not params & {"page_size", "page_cursor"}, (
        f"{name} is not paginated upstream but accepts paging arguments")
