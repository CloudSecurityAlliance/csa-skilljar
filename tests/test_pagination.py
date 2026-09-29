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
from csa_skilljar.v1backend import FakeV1Backend


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


def v1_backend():
    """Enough rows that the default page leaves more behind, for each v1 family."""
    return FakeV1Backend(
        promo_codes=[{"id": f"c{i}", "code": f"C{i}", "active": True,
                      "promo_code_pool_id": "p1"} for i in range(N)],
        promo_code_pools=[{"id": f"p{i}", "name": f"Pool {i}", "offer_id": f"o{i}"}
                          for i in range(N)],
        offers=[{"id": f"o{i}", "sku": f"SKU{i}"} for i in range(N)],
        credit_codes=[{"id": f"t{i}", "training_credit_code": f"T{i}"} for i in range(N)],
        assets=[{"id": f"a{i}", "name": f"a{i}.pdf", "type": "PDF"} for i in range(N)],
        paths=[{"id": f"pa{i}", "title": f"Path {i}"} for i in range(N)],
        path_items={f"pa{i}": [{"id": f"it{j}", "slug": f"s{j}"} for j in range(N)]
                    for i in range(N)},
        published_paths=[{"id": f"pp{i}", "_domain": "d", "path": {"id": "pa0"}}
                         for i in range(N)],
        course_series=[{"id": f"cs{i}", "title": f"Series {i}"} for i in range(N)],
        path_enrollments={"u1": [{"id": "pe1"}]},
        webhooks=[{"id": f"w{i}", "event_type": "COURSE_COMPLETION", "active": True,
                   "target_url": "https://x/h", "additional_headers": {}}
                  for i in range(N)],
        instructors=[{"name": f"I{i}", "email": f"i{i}@x.org", "providers": []}
                     for i in range(N)],
        ilt_sessions=[{"id": f"is{i}", "display_name": f"S{i}"} for i in range(N)],
        # `ends_at` and the nested lesson/course are what make the three filters on this
        # endpoint reachable - without them `"" <= bound` matched every row (#105).
        vilt_events=[{"id": f"ve{i}", "starts_at": "2026-01-01T00:00:00Z",
                      "ends_at": "2026-01-02T00:00:00Z",
                      "vilt_session": {"id": f"is{i}",
                                       "lesson": {"id": f"l{i}",
                                                  "course": {"id": f"c{i}"}}}}
                     for i in range(N)],
        vilt_registrations=[{"id": f"vr{i}", "attended": True,
                             "user": {"id": f"u{i}"}, "vilt_session": {"id": "is0"}}
                            for i in range(N)],
        labels=[{"id": f"lb{i}", "name": f"L{i}"} for i in range(N)],
        tags=[{"id": f"tg{i}", "name": f"T{i}", "slug": f"t{i}"} for i in range(N)],
        group_categories=[{"id": f"gc{i}", "name": f"C{i}"} for i in range(N)],
        course_labels={"c1": [{"id": "lb0", "name": "L0"}]},
    )


def tools():
    fake = backend()
    policy = Policy.from_profile("full")
    client = SkilljarClient(PolicyBackend(fake, policy),
                            v1=PolicyBackend(v1_backend(), policy))
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
                 "list_oauth_clients", "list_oauth_scopes",
                 # v1-only, and v1 pages by NUMBER with a total rather than by v2's
                 # opaque cursor - so these must not offer page_cursor/page_size, which
                 # would imply a control they cannot honour.
                 "list_learner_progress",
                 # v1 returns the whole asset library in one response.
                 "list_assets",
                 # One learner's path enrolments: a small bounded set, no paging offered.
                 "list_learner_path_enrollments",
                 # One course's labels: a small bounded set, no paging offered.
                 "list_course_labels"}

# A THIRD kind, which the original two categories had no room for. v1 pages by NUMBER
# with a total; v2 pages by opaque cursor with none. Lumping these in with "not
# paginated" would have asserted they take no paging arguments, which is false, and
# lumping them in with the cursor-paginated set would have demanded a `page_cursor` they
# do not have. Neither would have described what these tools actually do.
# name -> the arguments needed to reach a populated collection. A set was enough until
# Block 14, where three of these take a required identifier.
V1_PAGE_NUMBER = {
    "list_promo_codes": {}, "list_promo_code_pools": {}, "list_offers": {},
    "list_training_credit_codes": {},
    "list_webhooks": {},
    "list_ilt_instructors": {}, "list_ilt_sessions": {},
    "list_vilt_session_events": {}, "list_vilt_registrations": {},
    "list_labels": {}, "list_tags": {}, "list_group_categories": {},
    "list_paths": {}, "list_path_items": {"path_id": "pa0"},
    "list_published_paths": {"domain_name": "d"}, "list_course_series": {"domain_name": "d"},
}


def test_every_list_tool_is_classified():
    """Fail-closed. A list tool added next block lands in neither set and fails here,
    rather than shipping unpaginated-and-untested like five of these did."""
    registered = {n for n in tools()[0] if n.startswith("list_")}
    unclassified = sorted(registered - set(PAGINATED) - NOT_PAGINATED - set(V1_PAGE_NUMBER))
    assert not unclassified, f"new list tools with no pagination verdict: {unclassified}"
    stale = sorted((set(PAGINATED) | NOT_PAGINATED | set(V1_PAGE_NUMBER)) - registered)
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


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_v1_tools_page_by_number_not_cursor(name):
    """v1 and v2 paginate differently, and a tool must offer the one its backend has.
    Offering `page_cursor` on a v1 tool would be a control that cannot be honoured."""
    params = set(inspect.signature(tools()[0][name]).parameters)
    assert "page" in params and "page_size" in params
    assert "page_cursor" not in params, (
        f"{name} is served by v1, which has no cursors")


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_v1_tools_report_a_total(name):
    """The reason page numbers are tolerable here: v1 gives a count, so "how many" is
    answerable from one small page. v2 never provides one."""
    out = tools()[0][name](**V1_PAGE_NUMBER[name])
    assert "total" in out, f"{name} must surface v1's count"


# ---------------------------------------------------------------------------
# page_size=0 (#102)
# ---------------------------------------------------------------------------
# Twenty-nine tools take `page_size`. Nine did nothing with a zero, eleven rejected it
# inline, and nine more coerced it silently to the default - because `_size(0)` computes
# `0 or _DEFAULT`. Three behaviours for one argument on one surface, and no test anywhere
# asserted any of them: the inline guards could be deleted whole and the suite stayed green.
#
# The guard now lives in `_base.translate_errors`, which wraps every tool, so this census
# is what makes that structural rather than merely tidy: membership is read off the
# SIGNATURES, so a list tool added next block is covered without anyone remembering, and a
# tool that stops enforcing it fails here by name.

#: name -> arguments that get the call as far as the guard. Both paging families, since
#: the guard is about the argument rather than about which API serves it.
PAGE_SIZE_ARGS = {**{n: extra for n, (_key, extra) in PAGINATED.items()}, **V1_PAGE_NUMBER}


def takes_page_size():
    return {n for n, fn in tools()[0].items()
            if "page_size" in inspect.signature(fn).parameters}


def test_every_tool_taking_page_size_is_covered_here():
    """Fail-closed, and it is the half that matters. The defect was not that a guard was
    wrong, it was that nobody noticed nine tools never had one - which only a census over
    the whole population can see. A per-tool test passes forever on the tools that are
    already right."""
    uncovered = sorted(takes_page_size() - set(PAGE_SIZE_ARGS))
    assert not uncovered, f"tools taking page_size with no entry here: {uncovered}"
    stale = sorted(set(PAGE_SIZE_ARGS) - takes_page_size())
    assert not stale, f"entries here for tools that no longer take page_size: {stale}"


@pytest.mark.parametrize("name", sorted(PAGE_SIZE_ARGS))
def test_page_size_zero_is_refused_by_name(name):
    """Zero is a caller mistake in every case - it asks for no rows - so the answer is the
    same everywhere, and it names the argument so the model can correct itself rather than
    retrying the same call."""
    with pytest.raises(Exception, match="page_size"):
        tools()[0][name](page_size=0, **PAGE_SIZE_ARGS[name])


@pytest.mark.parametrize("name", sorted(PAGE_SIZE_ARGS))
def test_negative_page_size_is_refused_too(name):
    """The guard is `< 1` rather than `== 0`, and a bound stated one way and tested the
    other is how a check ends up passing the only value anyone tried."""
    with pytest.raises(Exception, match="page_size"):
        tools()[0][name](page_size=-1, **PAGE_SIZE_ARGS[name])


@pytest.mark.parametrize("name", sorted(PAGE_SIZE_ARGS))
def test_omitting_page_size_still_works(name):
    """The other side of the guard, and the reason it is `is not None` rather than a
    truthiness test: `None` means "no preference" and must still reach the default. A guard
    written as `if not page_size` would refuse every unpaginated call and this would catch
    it."""
    tools()[0][name](**PAGE_SIZE_ARGS[name])


# ---------------------------------------------------------------------------
# The v1 ceiling, and the v1 second page
# ---------------------------------------------------------------------------
# #102 moved the page_size FLOOR into `_base.translate_errors`, because it was identical on
# all twenty-nine tools. The CEILINGS stayed with their modules, because they are not: they
# are per-API, and commerce's carries a warning v1 earns by honouring page_size=1000 and
# returning a thousand rows into a conversation.
#
# Staying local is the right call and it is also how the floor drifted, so the ceilings get
# the census the floor now has.

_V1_MAX = 250


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_the_v1_ceiling_is_exact(name):
    """Both sides of the bound, because a limit tested only from far away is a limit whose
    off-by-one nobody has looked at. 250 is the documented maximum, so 250 must WORK - a
    ceiling that refuses its own stated value is the more annoying failure, and the one a
    test written with 100000 would never see."""
    fns = tools()[0]
    fns[name](page_size=_V1_MAX, **V1_PAGE_NUMBER[name])
    with pytest.raises(Exception, match="page_size"):
        fns[name](page_size=_V1_MAX + 1, **V1_PAGE_NUMBER[name])


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_a_v1_first_page_offers_the_next_page_number(name):
    """The v1 half of THE regression. v2 reports `has_more` with a cursor and v1 reports a
    page number, and a tool that drops the number strands the caller on page one holding a
    `total` that says there is more - which is worse than no total at all, because it is
    visibly incomplete and offers no way forward."""
    out = tools()[0][name](page_size=2, **V1_PAGE_NUMBER[name])
    assert out.get("total") == N, f"{name} lost v1's count"
    assert out.get("next_page") == 2, (
        f"{name} has {N} rows at page_size=2 and offers no next_page")


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_a_v1_last_page_offers_no_next_page(name):
    """The other half. A tool that always reports a next page makes a caller loop for ever,
    and asserting only the first page cannot tell the two apart."""
    out = tools()[0][name](page_size=_V1_MAX, **V1_PAGE_NUMBER[name])
    assert "next_page" not in out, (
        f"{name} returned every row and still offers a next page")
