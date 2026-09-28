"""Every filter on `FakeBackend` filters — in both directions.

The fake powers the whole unit suite, so a filter that is silently ignored does not fail a
test; it makes every test built on it weaker without saying so. `list_courses(title="zero")`
returning all three courses looks exactly like a test fixture with one course in it.

**Both directions are needed and the second is the one that gets skipped.** A filter that
returns nothing for every input passes "an impossible value yields no rows" perfectly. That is
`TESTING.md`'s negative-control rule — *a gate that refuses everything looks identical to one
that works* — applied to a query instead of a gate.

Measured 2026-09-28: all 36 single-value filters honour an impossible value, and none was
ignored. This pins that, so an added filter that forgets to filter fails here.
"""
from __future__ import annotations

import inspect

import pytest

from csa_skilljar.backend import FakeBackend

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


def call(method, **kwargs):
    backend = FakeBackend(**CONTAINERS)
    return getattr(backend, method)(**{**REQUIRED.get(method, {}), **kwargs})["data"]


def test_the_census_finds_the_filters():
    """The guard on the guard: a broken derivation would make every case below vacuous."""
    found = filters()
    assert len(found) >= 36, f"derived only {len(found)} filters; expected 36+"
    assert ("list_courses", "title") in found
    assert ("list_students", "email") in found


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
