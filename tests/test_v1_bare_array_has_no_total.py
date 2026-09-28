"""A v1 endpoint that does not say how many rows there are must not be reported as saying zero.

v1 answers in two envelope shapes, and `parse_page` says which is which:

    {"count": 42, "next": "...", "results": [...]}   paginated
    [ {...}, {...} ]                                 bare array

A bare array carries no count, so `parse_page` sets `total` to None - and its own comment
is explicit that this is *"different from a total of zero"*. Every v1 tool therefore guards
the key:

    if page.get("total") is not None:
        out["total"] = page["total"]

The guard is the whole point, and no test exercised its false arm: `FakeV1Backend` seeds
DRF envelopes, so `total` was always present and every one of those branches went one way
only. The fake's own docstring calls the two-envelope trap "the single most likely thing to
break here", and it was the half that was never driven.

Reporting `total: 0` for an endpoint that declined to count is worse than omitting it. A
caller reading `total` gets a number, and a number is a claim - "there are none" rather than
"this endpoint does not say".
"""
from __future__ import annotations

from typing import Any

import pytest

from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

from .test_pagination import V1_PAGE_NUMBER, v1_backend
from .test_pagination import backend as v2_backend


class BareArray:
    """The same v1 fixture, answering in the OTHER envelope.

    A wrapper rather than a second fixture: the rows must be identical, or a difference in
    the output could be the rows rather than the envelope, and this would be testing two
    things at once.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def answering_as_a_bare_array(**kwargs: Any) -> Any:
            page = attr(**kwargs)
            if isinstance(page, dict) and "rows" in page:
                # Exactly what `parse_page` produces for a JSON array: the rows, and no
                # claim at all about how many there are in total or where the next ones are.
                return {**page, "total": None, "has_more": False, "next_page": None}
            return page

        return answering_as_a_bare_array


def tools():
    policy = Policy.from_profile("full")
    client = SkilljarClient(PolicyBackend(v2_backend(), policy),
                            v1=PolicyBackend(BareArray(v1_backend()), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_an_uncounted_page_omits_total_rather_than_reporting_none(name):
    """`total: null` in a JSON-RPC result is a field the caller has to know to ignore.
    Omitting it says the same thing in the one way every client already understands."""
    out = tools()[name](**V1_PAGE_NUMBER[name])
    assert "total" not in out, (
        f"{name} reported total={out.get('total')!r} for an endpoint that returned a bare "
        f"array and therefore never said how many rows exist")


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_an_uncounted_page_still_returns_its_rows(name):
    """The guard must drop the KEY, not the answer. A tool that returned nothing when the
    count was absent would pass the case above perfectly."""
    out = tools()[name](**V1_PAGE_NUMBER[name])
    rows = next((v for v in out.values() if isinstance(v, list)), None)
    assert rows, f"{name} returned no rows at all when the envelope carried no count"


@pytest.mark.parametrize("name", sorted(V1_PAGE_NUMBER))
def test_an_uncounted_page_offers_no_next_page(name):
    """A bare array has no `next` URL either, so there is no page number to offer. Emitting
    one would send the caller to a page the endpoint never promised."""
    out = tools()[name](**V1_PAGE_NUMBER[name])
    assert "next_page" not in out
    assert out.get("has_more") is False


# ---------------------------------------------------------------------------
# The two v1 reads that are not list_ tools
# ---------------------------------------------------------------------------
# `list_learner_progress` and `find_learner` guard `total` the same way, and neither is in
# `V1_PAGE_NUMBER` - one is classified as unpaginated and the other is a lookup. Their own
# seed rather than an addition to the shared fixture, which two hundred other cases depend
# on being exactly the size it is.


def progress_tools():
    policy = Policy.from_profile("full")
    v1 = FakeV1Backend(
        progress={"u1": [{"id": "pr1", "published_course": {"id": "pc1", "title": "T"},
                          "progress": 50}]},
        users=[{"id": "u1", "email": "learner@example.org"}])
    client = SkilljarClient(PolicyBackend(v2_backend(), policy),
                            v1=PolicyBackend(BareArray(v1), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


def test_learner_progress_omits_total_when_the_envelope_carries_none():
    out = progress_tools()["list_learner_progress"](user_id="u1")
    assert out["progress"], "the rows went missing along with the count"
    assert "total" not in out


def test_find_learner_omits_total_when_the_envelope_carries_none():
    """A lookup by address. Reporting `total: 0` beside a list holding one learner would be
    a contradiction the caller has to resolve."""
    out = progress_tools()["find_learner"](email="learner@example.org")
    assert "total" not in out


def test_learner_progress_never_reports_a_total_at_all():
    """Not "has not yet" - CANNOT. `/v1/users/{id}/published-courses` answers with a bare
    array unconditionally, which `V1Backend.list_learner_progress` records at the line that
    parses it: *"A BARE ARRAY, as the real endpoint sends. No count, no next."*

    So this tool's `if page.get("total") is not None` has a true arm that production can
    never reach, and coverage found it by being unable to reach it either. That line carries
    a pragma naming this test; if Skilljar ever paginates the endpoint, this case fails and
    the pragma comes off together.
    """
    policy = Policy.from_profile("full")
    v1 = FakeV1Backend(
        progress={"u1": [{"id": "pr1", "published_course": {"id": "pc1", "title": "T"},
                          "progress": 50}]},
        users=[{"id": "u1", "email": "learner@example.org"}])
    assert v1.list_learner_progress(user_id="u1")["total"] is None, (
        "the endpoint now reports a count - remove the pragma in progress.py and assert the "
        "tool surfaces it")

    client = SkilljarClient(PolicyBackend(v2_backend(), policy),
                            v1=PolicyBackend(v1, policy))       # NOT wrapped
    app = create_server(lambda: client, settings=settings_from_env({}))
    out = {n: t.fn for n, t in app._tool_manager._tools.items()}["list_learner_progress"](
        user_id="u1")
    assert out["progress"], "the rows must survive the absent count"
    assert "total" not in out
