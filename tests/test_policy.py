import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar import policy as P
from csa_skilljar.backend import Backend, FakeBackend

ROWS = [{"type": "courses", "id": "c1", "attributes": {"title": "t"}}]


def test_every_backend_method_has_a_declared_gate():
    """Fails CI when the protocol grows past the gate table. The direction of the
    default matters more than the test: an undeclared method is REFUSED, not delegated."""
    methods = {n for n in dir(Backend) if not n.startswith("_")}
    assert methods <= set(P._GATES), f"undeclared: {sorted(methods - set(P._GATES))}"


def test_undeclared_method_is_refused_not_delegated():
    class Grown(FakeBackend):
        def delete_everything(self, *, id: str) -> dict:
            return {"boom": True}

    pb = P.PolicyBackend(Grown(), P.Policy.from_profile("full"))
    with pytest.raises(exc.PolicyError):
        pb.delete_everything(id="x")


def test_read_passes_through_when_capability_is_enabled():
    pb = P.PolicyBackend(FakeBackend(courses=ROWS), P.Policy.from_profile("parity"))
    assert pb.list_courses()["data"][0]["id"] == "c1"


def test_disabled_capability_is_refused():
    pb = P.PolicyBackend(FakeBackend(), P.Policy(frozenset()))
    with pytest.raises(exc.PolicyError) as e:
        pb.list_courses()
    assert "content.read" in str(e.value)


def test_refusal_names_the_setting_the_operator_would_change():
    pb = P.PolicyBackend(FakeBackend(), P.Policy(frozenset()))
    with pytest.raises(exc.PolicyError) as e:
        pb.list_courses()
    assert "CSA_SKILLJAR_PROFILE" in str(e.value)


def test_one_capability_at_a_time_matrix():
    """Hand-written, NEVER derived from _GATES. Deriving it tests the table against
    itself and passes no matter what the table says."""
    expected = {"content.read": {"list_courses"}}
    every_method = {"list_courses"}
    for cap in P.ALL_CAPABILITIES:
        allowed = expected.get(cap, set())
        pb = P.PolicyBackend(FakeBackend(courses=ROWS), P.Policy(frozenset({cap})))
        for name in every_method:
            if name in allowed:
                getattr(pb, name)()
            else:
                with pytest.raises(exc.PolicyError):
                    getattr(pb, name)()


def test_unknown_profile_is_a_loud_error_not_a_silent_default():
    with pytest.raises(ValueError):
        P.Policy.from_profile("editorr")


def test_profiles_are_all_subsets_of_full():
    for name, caps in P.PROFILES.items():
        assert set(caps) <= set(P.ALL_CAPABILITIES), f"{name} names an unknown capability"


def test_policy_is_reachable_for_inspection():
    pol = P.Policy.from_profile("parity")
    assert P.PolicyBackend(FakeBackend(), pol).policy is pol
