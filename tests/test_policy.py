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


# Hand-written. NEVER derive this from _GATES: deriving it tests the table against
# itself and passes no matter what the table says. A gate wired to the WRONG capability
# is invisible to any test that reads _GATES, and that is the bug this exists to catch.
EXPECTED_BY_CAPABILITY = {
    "content.read": {"list_courses", "get_course", "list_lessons", "get_lesson",
                     "list_quizzes", "get_quiz"},
    "content.write": {"create_courses", "update_courses",
                      "create_lessons", "update_lessons",
                      "create_quizzes", "update_quizzes"},
    # Deliberately NOT in content.write: an authoring credential must not be able to
    # destroy what it can create.
    "content.delete": {"delete_quizzes"},
}

# Arguments good enough to reach the gate. A NotFound from the fake means the gate
# OPENED, which is what is being asserted.
CALL_ARGS = {
    "list_courses": {}, "get_course": {"course_id": "c1"},
    "list_lessons": {}, "get_lesson": {"lesson_id": "l1"},
    "create_courses": {"items": []}, "update_courses": {"items": []},
    "create_lessons": {"items": []}, "update_lessons": {"items": []},
    "list_quizzes": {}, "get_quiz": {"quiz_id": "q1"},
    "create_quizzes": {"items": []}, "update_quizzes": {"items": []},
    "delete_quizzes": {"quiz_ids": []},
}


def test_the_matrix_covers_every_gated_method():
    """If a block adds a Backend method and forgets the matrix, that is a hole."""
    covered = set().union(*EXPECTED_BY_CAPABILITY.values())
    assert covered == set(P._GATES), (
        f"matrix and _GATES disagree: {sorted(covered ^ set(P._GATES))}"
    )


def test_one_capability_at_a_time_matrix():
    """Enable exactly one capability; assert precisely which operations become possible."""
    every_method = set().union(*EXPECTED_BY_CAPABILITY.values())
    for cap in P.ALL_CAPABILITIES:
        allowed = EXPECTED_BY_CAPABILITY.get(cap, set())
        pb = P.PolicyBackend(FakeBackend(courses=ROWS), P.Policy(frozenset({cap})))
        for name in sorted(every_method):
            if name in allowed:
                try:
                    getattr(pb, name)(**CALL_ARGS[name])
                except exc.PolicyError:
                    pytest.fail(f"{cap} should permit {name} but it was refused")
                except exc.SkilljarError:
                    pass          # not-found from the fake: the GATE opened, which is the point
            else:
                with pytest.raises(exc.PolicyError):
                    getattr(pb, name)(**CALL_ARGS[name])


def test_no_capability_is_an_accidental_superset_of_another():
    read_only = P.PolicyBackend(FakeBackend(courses=ROWS),
                                P.Policy(frozenset({P.READ_CONTENT})))
    with pytest.raises(exc.PolicyError):
        read_only.create_courses(items=[])
    write_only = P.PolicyBackend(FakeBackend(courses=ROWS),
                                 P.Policy(frozenset({P.WRITE_CONTENT})))
    with pytest.raises(exc.PolicyError):
        write_only.list_courses()


def test_unknown_profile_is_a_loud_error_not_a_silent_default():
    with pytest.raises(ValueError):
        P.Policy.from_profile("editorr")


def test_profiles_are_all_subsets_of_full():
    for name, caps in P.PROFILES.items():
        assert set(caps) <= set(P.ALL_CAPABILITIES), f"{name} names an unknown capability"


def test_policy_is_reachable_for_inspection():
    pol = P.Policy.from_profile("parity")
    assert P.PolicyBackend(FakeBackend(), pol).policy is pol
