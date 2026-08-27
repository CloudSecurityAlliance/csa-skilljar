"""Read-only against a real Skilljar organization. Nothing here writes."""
from __future__ import annotations

import pytest

from csa_skilljar import exceptions as exc


def test_a_token_is_granted_and_carries_scopes(live_client):
    creds = live_client.credentials
    assert creds is not None
    assert creds.granted_scopes(), "the token carried no scopes"
    remaining = creds.expires_in()
    assert remaining is not None and remaining > 0


def test_the_token_never_appears_in_its_own_repr(live_client):
    """The one place a real credential exists in memory."""
    creds = live_client.credentials
    assert "***" in repr(creds)


def test_list_courses_returns_real_courses(live_client):
    env = live_client.list_courses(page_size=5)
    assert env["data"], "the organization has no courses"
    assert "title" in env["data"][0]["attributes"]


def test_pagination_actually_pages(live_client):
    """Only provable against the real API. FakeBackend's cursor is an integer index;
    Skilljar's is an opaque token, so the fake cannot prove the round trip works."""
    first = live_client.list_courses(page_size=1)
    if not first["has_more"]:
        pytest.skip("organization has fewer than two courses")
    assert first["next_cursor"], "has_more is true but no cursor was returned"
    second = live_client.list_courses(page_size=1, cursor=first["next_cursor"])
    assert second["data"], "the second page was empty"
    assert second["data"][0]["id"] != first["data"][0]["id"]


def test_get_course_round_trips_a_real_id(live_client):
    listed = live_client.list_courses(page_size=1)["data"][0]
    fetched = live_client.get_course(course_id=listed["id"])["data"]
    assert fetched["id"] == listed["id"]
    assert fetched["attributes"]["title"] == listed["attributes"]["title"]


def test_lessons_can_be_listed_for_a_real_course(live_client):
    course = live_client.list_courses(page_size=1)["data"][0]
    env = live_client.list_lessons(course_id=course["id"], page_size=5)
    assert "data" in env
    for row in env["data"]:
        assert row["attributes"]["course_id"] == course["id"]


def test_an_unknown_id_is_a_typed_not_found(live_client):
    """The fake raises NotFoundError directly; the real backend has to translate a 404.
    Those are different code paths and only this proves the second one."""
    with pytest.raises(exc.NotFoundError):
        live_client.get_course(course_id="definitely-not-a-real-id")


def test_a_scope_the_client_lacks_is_refused_before_any_request(live_client):
    """The pre-check must fire locally. If the client happens to hold every scope this
    skips rather than silently proving nothing."""
    creds = live_client.credentials
    granted = set(creds.granted_scopes())
    missing = next((s for s in ("students:anonymize", "clients:write", "webhooks:write")
                    if s not in granted), None)
    if missing is None:
        pytest.skip("this client holds every scope we would test the refusal with")
    with pytest.raises(exc.ScopeError) as e:
        creds.require_scope(missing)
    assert e.value.required == missing
