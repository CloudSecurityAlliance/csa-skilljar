"""Every filter on `FakeBackend` filters — in both directions.

The fake powers the whole unit suite, so a filter that is silently ignored does not fail a
test; it makes every test built on it weaker without saying so. `list_courses(title="zero")`
returning all three courses looks exactly like a test fixture with one course in it.

**Both directions are needed and the second is the one that gets skipped.** A filter that
returns nothing for every input passes "an impossible value yields no rows" perfectly. That is
`TESTING.md`'s negative-control rule — *a gate that refuses everything looks identical to one
that works* — applied to a query instead of a gate.

**And a census needs a non-empty baseline, or it proves nothing.** The first version of this
file ran every case against `FakeBackend(**CONTAINERS)`, which seeds only `groups`. So for 38
of the 40 filters the UNFILTERED call already returned `[]`, and `assert filtered == []` was
satisfied by there being nothing to return rather than by the filter working (#103). It hid
ten filters the fake ignored outright - all five on `list_certificates`, three on
`list_enrollments`, and both on `list_course_ratings`.

Membership and potency are different properties. Deriving membership from the signatures gets
every filter enumerated for free; it says nothing about whether any case can fail. So each
filter now has TWO cases: the baseline returns rows, and the impossible value does not.

Measured 2026-09-28, seeded: 40 filters, all 40 with a non-empty baseline, all 40 honouring an
impossible value.
"""
from __future__ import annotations

import inspect

import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.backend import FakeBackend
from csa_skilljar.v1backend import FakeV1Backend

from .test_pagination import v1_backend as v1_seed

#: `include` is a sideload directive, not a filter — it adds related rows rather than removing
#: any, so "an impossible value returns nothing" is the wrong property for it.
NOT_A_FILTER = {"include"}

#: A boolean cannot have an impossible value: both arms are meaningful. Tested separately by
#: asserting the two arms PARTITION, which is the property that actually matters for them.
BOOLEAN = {"active", "live", "is_inactive", "is_visible"}

#: Required arguments a list method needs before any filter is reachable.
REQUIRED = {
    "list_course_ratings": {"course_id": "c1"},
    "list_visibility_overrides": {"group_id": "g1"},
    "list_path_items": {"path_id": "p1"},
}

#: Some of those containers must EXIST, not merely be named — `list_visibility_overrides`
#: resolves the group before it filters, and a missing one raises rather than returning empty.
#: That is the container-versus-item distinction again, and it means an empty backend is not a
#: neutral starting point for every method.
CONTAINERS = {"groups": [{"type": "groups", "id": "g1", "attributes": {"name": "G"}}]}

#: Every collection a filtered method reads, seeded with one row that carries every attribute
#: any filter on that collection matches against. Attribute names are NOT derivable from
#: parameter names - `student_email` matches `email`, `issued_gte` matches `issued_at`,
#: `course_id` matches `published_course_id` - so this is written out, and
#: `test_every_filter_has_a_non_empty_baseline` is what stops it rotting: a collection that
#: stops being seeded fails there by name instead of quietly making its filters untestable.
SEED: dict[str, list[dict]] = {
    "groups": [{"type": "groups", "id": "g1", "attributes": {
        "name": "G", "rule_email_domains": []}}],
    "courses": [{"type": "courses", "id": "c1", "attributes": {
        "title": "Zero Trust", "is_published": True}}],
    "lessons": [{"type": "lessons", "id": "l1", "attributes": {
        "title": "L", "course_id": "c1", "lesson_type": "VIDEO"}}],
    "quizzes": [{"type": "quizzes", "id": "qz1", "attributes": {
        "name": "Q", "course_id": "c1"}}],
    "questions": [{"type": "questions", "id": "qn1", "attributes": {
        "quiz_id": "qz1", "question_html": "<p>?</p>", "question_type": "FREEFORM",
        "answers": []}}],
    "question_banks": [{"type": "question-banks", "id": "qb1", "attributes": {"name": "B"}}],
    "enrollments": [{"type": "enrollments", "id": "e1", "attributes": {
        "active": True, "progress_status": "completed", "course_id": "c1",
        "published_course_id": "pc1", "student_id": "s1", "email": "s1@example.org",
        "domain_name": "d1.example.org", "enrolled_at": "2026-02-01T00:00:00Z",
        "completed_at": "2026-02-02T00:00:00Z"}}],
    "certificates": [{"type": "certificates", "id": "cert1", "attributes": {
        "status": "active", "course_id": "c1", "published_course_id": "pc1",
        "student_id": "s1", "domain_name": "d1.example.org",
        "issued_at": "2026-02-01T00:00:00Z"}}],
    "course_ratings": [{"type": "course-ratings", "id": "r1", "attributes": {
        "course_id": "c1", "student_id": "s1", "rating": 5, "feedback": "good"}}],
    "students": [{"type": "students", "id": "s1", "attributes": {
        "email": "s1@example.org", "first_name": "A", "last_name": "B",
        "is_inactive": False}}],
    "signup_field_values": [{"type": "signup-field-values", "id": "v1", "attributes": {
        "label": "Job", "value": "x"},
        "relationships": {"student": {"data": {"type": "students", "id": "s1"}}}}],
    "published_courses": [{"type": "published-courses", "id": "pc1", "attributes": {
        "title": "Zero Trust", "course_id": "c1", "domain_name": "d1.example.org",
        "is_visible": True}}],
    "domains": [{"type": "domains", "id": "d1", "attributes": {
        "name": "d1.example.org", "is_default": True}}],
    "web_packages": [{"type": "web-packages", "id": "wp1", "attributes": {
        "content_url": "https://example.org/p"}}],
}


def impossible(name: str):
    """A value of the right shape that nothing in any fixture can match.

    `domains` is a COMMA-SEPARATED STRING rather than a list — Skilljar's own filter convention,
    and passing a list raises `AttributeError` on `.split`. Worth encoding here because it is
    the shape a caller gets wrong first.
    """
    if name.endswith(("_gte", "_since")):
        return "2999-01-01T00:00:00Z"
    if name.endswith("_lte"):
        return "1900-01-01T00:00:00Z"
    if name == "domains":
        return "no-such-domain"
    if name.endswith("status") or name == "lesson_type":
        return "NO_SUCH_VALUE"
    return "zzz-no-such-value-zzz"


def filters() -> list[tuple[str, str]]:
    """(method, filter parameter) for every filter on every `list_*`, derived."""
    found = []
    for name in sorted(n for n in dir(FakeBackend) if n.startswith("list_")):
        for param, spec in inspect.signature(getattr(FakeBackend, name)).parameters.items():
            if param in ("self", "cursor", "page_size") or param in NOT_A_FILTER:
                continue
            if spec.default is inspect.Parameter.empty or param in BOOLEAN:
                continue
            found.append((name, param))
    return found


def seeded() -> FakeBackend:
    """A backend with every filtered collection populated.

    Visibility overrides have no constructor argument - they live in a side table keyed by
    (group, published course, visibility) and exist only once created - so that one is seeded
    through the API. A collection that cannot be expressed in `SEED` still has to be seeded
    SOMEWHERE, or its filters are untestable; the baseline guard is what says which.
    """
    backend = FakeBackend(**SEED)
    backend.add_visibility_overrides(
        group_id="g1", items=[{"published_course_id": "pc1", "is_visible": True}])
    return backend


def call(method, **kwargs):
    """One filtered call against a FULLY seeded backend.

    A fresh backend per call: several of these methods mutate, and a shared one would make
    the result depend on test order.
    """
    return getattr(seeded(), method)(**{**REQUIRED.get(method, {}), **kwargs})["data"]


def test_the_census_finds_the_filters():
    """The guard on the guard: a broken derivation would make every case below vacuous."""
    found = filters()
    assert len(found) >= 36, f"derived only {len(found)} filters; expected 36+"
    assert ("list_courses", "title") in found
    assert ("list_students", "email") in found


@pytest.mark.parametrize("method, param", filters(), ids=lambda v: v if isinstance(v, str) else v)
def test_every_filter_has_a_non_empty_baseline(method, param):
    """The potency guard, and the case whose absence made this whole file decorative.

    `assert filtered == []` is satisfied by a filter that works AND by a fixture with nothing
    in it, and those are indistinguishable from the assertion alone. This is the half that
    tells them apart, per filter and by name, so a collection that stops being seeded fails
    here rather than silently draining the case below of its meaning."""
    assert call(method), (
        f"{method} returns nothing before {param} is applied, so the case below cannot fail. "
        f"Seed {method}'s collection in SEED.")


@pytest.mark.parametrize("method, param", filters(), ids=lambda v: v if isinstance(v, str) else v)
def test_a_value_nothing_can_match_returns_nothing(method, param):
    """Direction one. A filter that is ignored returns the whole table here."""
    assert call(method, **{param: impossible(param)}) == []


class TestTheOtherDirection:
    """Direction two, on a seeded backend. Without these, a filter hard-wired to return nothing
    would pass every case above."""

    @staticmethod
    def courses():
        return FakeBackend(courses=[
            {"type": "courses", "id": "c1", "attributes": {"title": "Zero Trust"}},
            {"type": "courses", "id": "c2", "attributes": {"title": "AI Security"}}])

    def test_a_matching_filter_returns_only_the_match(self):
        got = self.courses().list_courses(title="zero")["data"]
        assert [c["id"] for c in got] == ["c1"]

    def test_no_filter_returns_everything(self):
        assert len(self.courses().list_courses()["data"]) == 2

    def test_the_filter_is_case_insensitive_and_partial(self):
        """Both are deliberate and both are load-bearing: a caller filtering on a title typed
        from memory gets the row, and one filtering on an exact title still does."""
        backend = self.courses()
        assert len(backend.list_courses(title="ZERO TRUST")["data"]) == 1
        assert len(backend.list_courses(title="Trust")["data"]) == 1


class TestBooleanFiltersPartition:
    """A boolean filter has no impossible value, so the property is that the two arms divide the
    rows rather than that one of them is empty. A boolean that is ignored returns everything for
    both — which is what this catches and the impossible-value test cannot."""

    @staticmethod
    def students():
        return FakeBackend(students=[
            {"type": "students", "id": "s1", "attributes": {"is_inactive": False}},
            {"type": "students", "id": "s2", "attributes": {"is_inactive": True}}])

    def test_the_two_arms_divide_the_rows(self):
        backend = self.students()
        active = backend.list_students(is_inactive=False)["data"]
        inactive = backend.list_students(is_inactive=True)["data"]
        everyone = backend.list_students()["data"]

        assert len(everyone) == 2
        assert {s["id"] for s in active} | {s["id"] for s in inactive} == {"s1", "s2"}
        assert {s["id"] for s in active} & {s["id"] for s in inactive} == set(), (
            "the two arms overlap, so the filter is not partitioning")
        assert len(active) < len(everyone), "the filter returned everything for one arm"


# ---------------------------------------------------------------------------
# Required selectors (#103)
# ---------------------------------------------------------------------------
# `filters()` skips any parameter with no default — that is the rule for "optional filter",
# and it excluded the REQUIRED ones: `course_id` on `list_course_ratings`, on
# `get_course_analytics`. Both were ignored, and neither was in the census.
#
# A required selector that is ignored is strictly worse than an optional filter that is
# ignored. An optional filter left out returns too much, which a caller can see. A required
# selector left out returns another parent's rows under the name of the one you asked for —
# `get_course_analytics("TOTALLY-BOGUS")` answered with an enrolment count. That is not too
# much data, it is a confident wrong answer.


def selectors() -> list[tuple[str, str]]:
    """(method, required id parameter) for every read that names a parent, derived."""
    found = []
    for name in sorted(n for n in dir(FakeBackend) if n.startswith(("list_", "get_"))):
        for param, spec in inspect.signature(getattr(FakeBackend, name)).parameters.items():
            if param == "self" or spec.default is not inspect.Parameter.empty:
                continue
            if spec.annotation not in ("str", str):
                continue
            found.append((name, param))
    return found


def test_the_selector_census_is_not_empty():
    """The same guard the filter census needed, for the same reason: a derivation that
    silently matches nothing turns every case below into a pass."""
    found = selectors()
    assert len(found) >= 15, f"derived only {len(found)} selectors; expected 15+"
    assert ("get_course_analytics", "course_id") in found
    assert ("list_course_ratings", "course_id") in found


@pytest.mark.parametrize("method, param", selectors(),
                         ids=lambda v: v if isinstance(v, str) else v)
def test_a_bogus_parent_yields_nothing_rather_than_everything(method, param):
    """Raising and returning empty are both correct - they say "not here" in different
    dialects, and which one a method uses is a property of the endpoint. Returning ROWS is
    the failure, because those rows belong to some other parent."""
    args = {**REQUIRED.get(method, {}), param: "zzz-no-such-parent-zzz"}
    args = {k: v for k, v in args.items()
            if k in inspect.signature(getattr(FakeBackend, method)).parameters}
    try:
        data = getattr(seeded(), method)(**args)["data"]
    except exc.NotFoundError:
        return                      # said "not here", which is the whole point
    assert not data, (
        f"{method} returned {len(data) if isinstance(data, list) else 'an object'} for a "
        f"{param} that exists nowhere - so it is ignoring {param}, and every test scoped "
        f"to a parent through this method is vacuous")


# ---------------------------------------------------------------------------
# The other backend (#105)
# ---------------------------------------------------------------------------
# Everything above derives its membership from `FakeBackend`:
#
#     for name in sorted(n for n in dir(FakeBackend) if n.startswith("list_")):
#
# There are two backends. `FakeV1Backend` was never in scope, and three of its filters
# accepted a value and did nothing with it - the parameter in the signature, no filtering
# code at all.
#
# That is the SECOND time this census's blast radius was set by its membership rule rather
# than by its assertions: #103 excluded required selectors because they had no default, and
# this excluded a whole backend because the loop names one class. The assertions were right
# both times. **The set is the thing to review.**

#: v1 has no `include` and pages by number, so the exclusions differ from v2's.
V1_NOT_A_FILTER = {"self", "page", "page_size", "cursor", "include"}

#: `active` is the only boolean on the v1 surface, and a boolean has no impossible value -
#: both arms mean something. Same reasoning as `BOOLEAN` above.
V1_BOOLEAN = {"active"}


def v1_impossible(name: str):
    """v1 names its date bounds `_before` / `_after`, where v2 uses `_lte` / `_gte`. A value
    of the wrong SHAPE is the classic way to make a filter census report a pass: compare a
    date column against `"zzz"` and every row is less than it."""
    if name.endswith(("_before", "_lte")):
        return "1900-01-01T00:00:00Z"
    if name.endswith(("_after", "_gte", "_since")):
        return "2999-01-01T00:00:00Z"
    return "zzz-no-such-value-zzz"


def v1_filters() -> list[tuple[str, str]]:
    found = []
    for name in sorted(n for n in dir(FakeV1Backend) if n.startswith("list_")):
        for param, spec in inspect.signature(getattr(FakeV1Backend, name)).parameters.items():
            if param in V1_NOT_A_FILTER or param in V1_BOOLEAN:
                continue
            if spec.default is inspect.Parameter.empty:
                continue
            found.append((name, param))
    return found


def v1_call(method: str, **kwargs):
    backend = v1_seed()
    sig = inspect.signature(getattr(backend, method))
    required = {p.name: "x" for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty}
    return getattr(backend, method)(**{**required, **kwargs})["rows"]


def test_the_v1_census_finds_its_filters():
    found = v1_filters()
    assert len(found) >= 12, f"derived only {len(found)} v1 filters; expected 12+"
    assert ("list_vilt_session_events", "lesson_id") in found
    assert ("list_promo_code_pools", "offer_id") in found


@pytest.mark.parametrize("method, param", v1_filters(),
                         ids=lambda v: v if isinstance(v, str) else v)
def test_every_v1_filter_has_a_non_empty_baseline(method, param):
    """The same potency guard, for the same reason. It is what makes the case below able to
    fail, and `ends_before` is the argument for it: that filter WAS implemented and still
    matched every row, because the fixture carried no `ends_at` and `"" <= bound` is true."""
    assert v1_call(method), (
        f"{method} returns nothing before {param} is applied, so the case below cannot fail")


@pytest.mark.parametrize("method, param", v1_filters(),
                         ids=lambda v: v if isinstance(v, str) else v)
def test_a_v1_filter_that_matches_nothing_returns_nothing(method, param):
    assert v1_call(method, **{param: v1_impossible(param)}) == []
