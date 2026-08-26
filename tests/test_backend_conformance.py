import inspect

import pytest

from csa_skilljar.backend import Backend, FakeBackend, V2Backend

IMPLEMENTATIONS = [FakeBackend, V2Backend]


@pytest.mark.parametrize("impl", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_implementation_matches_the_protocol_signature_for_signature(impl):
    """The fake powers every unit test. If it drifts from the protocol the whole suite
    exercises a stale double; if the real backend drifts, the fake tests prove nothing
    about production. Compare signatures rather than trusting either."""
    for name in (n for n in dir(Backend) if not n.startswith("_")):
        proto = inspect.signature(getattr(Backend, name))
        got = inspect.signature(getattr(impl, name))
        assert proto == got, f"{impl.__name__}.{name} drifted: protocol {proto} vs {got}"


@pytest.mark.parametrize("impl", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_implementation_covers_every_protocol_method(impl):
    missing = {n for n in dir(Backend) if not n.startswith("_")} - set(dir(impl))
    assert not missing, f"{impl.__name__} is missing: {sorted(missing)}"


def test_fake_returns_a_jsonapi_envelope():
    b = FakeBackend(courses=[{"type": "courses", "id": "c1", "attributes": {"title": "Zero Trust"}}])
    out = b.list_courses()
    assert out["data"][0]["id"] == "c1"
    assert out["has_more"] is False
    assert out["next_cursor"] is None


def test_fake_filters_by_title_case_insensitively():
    b = FakeBackend(courses=[
        {"type": "courses", "id": "c1", "attributes": {"title": "Zero Trust"}},
        {"type": "courses", "id": "c2", "attributes": {"title": "AI Security"}},
    ])
    assert [c["id"] for c in b.list_courses(title="zero")["data"]] == ["c1"]


def test_fake_paginates_and_reports_more():
    b = FakeBackend(courses=[
        {"type": "courses", "id": f"c{i}", "attributes": {"title": str(i)}} for i in range(5)
    ])
    page = b.list_courses(page_size=2)
    assert len(page["data"]) == 2
    assert page["has_more"] is True
    assert page["next_cursor"] == "2"
    rest = b.list_courses(page_size=2, cursor=page["next_cursor"])
    assert [c["id"] for c in rest["data"]] == ["c2", "c3"]
