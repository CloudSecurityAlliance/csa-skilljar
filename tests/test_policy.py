import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar import policy as P
from csa_skilljar.backend import Backend, FakeBackend
from csa_skilljar.v1backend import FakeV1Backend

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
                     "list_quizzes", "get_quiz",
                     "list_questions", "get_question",
                     "list_question_banks", "get_question_bank",
                     "list_bank_assignments",
                     # v1-only: an asset IS content, and list_lessons already returns
                     # content_asset_id under this same capability.
                     "list_assets", "get_asset",
                     # Block 14 - a path is a course sequence, i.e. content.
                     "list_paths", "get_path", "list_path_items",
                     "list_published_paths", "list_course_series"},
    "reporting.read": {"list_enrollments", "get_enrollment", "list_certificates",
                       "get_certificate", "get_course_analytics",
                       "list_course_ratings"},
    "enrolment.write": {"update_enrollments", "complete_enrollments",
                        "bulk_enroll"},
    "people.read": {"list_students", "get_student"},
    "people.write": {"create_students", "update_students"},
    # Deliberately NOT in people.write: a credential for routine learner administration
    # must not be able to erase anyone or take over their account.
    "people.destructive": {"anonymize_student", "deactivate_student",
                           "set_student_password", "send_password_reset"},
    "content.write": {"create_courses", "update_courses",
                      "create_lessons", "update_lessons",
                      "create_quizzes", "update_quizzes",
                      "create_questions", "update_questions",
                      "create_question_banks", "update_question_banks",
                      "bind_banks", "update_bank_assignments", "unbind_banks"},
    # Deliberately NOT in content.write: an authoring credential must not be able to
    # destroy what it can create.
    "content.delete": {"delete_quizzes", "delete_questions",
                       "delete_question_banks"},
    "groups.read": {"list_groups", "get_group",
                    "list_signup_field_values", "get_signup_field_value",
                    # Visibility overrides live here, not under publishing.*: upstream
                    # gates them with student-groups:* and hangs them off the group.
                    "list_visibility_overrides"},
    "groups.write": {"create_groups", "update_groups",
                     "add_group_memberships", "remove_group_memberships",
                     "create_signup_field_values", "update_signup_field_values",
                     "add_visibility_overrides", "remove_visibility_overrides"},
    # Deliberately NOT in groups.write: deleting a group is a HARD delete and takes its
    # memberships and course-visibility overrides with it at the database level.
    "groups.delete": {"delete_groups"},
    "commerce.read": {"list_promo_codes", "list_promo_code_pools", "list_offers",
                      "list_training_credit_codes", "get_purchase"},
    "publishing.read": {"list_published_courses", "get_published_course",
                        "list_domains", "get_domain"},
    # v1-only, and gated by the SAME table as every v2 method.
    "progress.read": {"find_learner", "list_learner_progress", "get_learner_progress",
                      "list_learner_path_enrollments"},
    # Deliberately NOT reachable from `authoring`: these change what anonymous visitors
    # to a customer-facing site can see.
    "publishing.write": {"publish_courses", "update_published_courses",
                         "delete_published_course", "unpublish_published_course",
                         "republish_published_course"},
    "webpackages.read": {"list_web_packages", "get_web_package"},
    "webpackages.write": {"create_web_packages", "update_web_packages",
                          "delete_web_package"},
    # Mints a credential, so it needs `admin` named explicitly - the official server
    # ships it enabled.
    "admin.credentials": {"register_oauth_client",
                          # Block 10 - audit and remediation, gated as hard as minting.
                          "list_oauth_clients", "get_oauth_client",
                          "create_oauth_client", "update_oauth_client",
                          "deactivate_oauth_client", "rotate_oauth_client_secret",
                          "list_oauth_scopes", "revoke_refresh_token"},
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
    "list_questions": {}, "get_question": {"question_id": "qu1"},
    "create_questions": {"items": []}, "update_questions": {"items": []},
    "delete_questions": {"question_ids": []},
    "list_question_banks": {}, "get_question_bank": {"bank_id": "b1"},
    "create_question_banks": {"items": []}, "update_question_banks": {"items": []},
    "delete_question_banks": {"bank_ids": []},
    "list_bank_assignments": {"quiz_id": "q1"},
    "bind_banks": {"quiz_id": "q1", "items": []},
    "update_bank_assignments": {"quiz_id": "q1", "items": []},
    "unbind_banks": {"quiz_id": "q1", "items": []},
    "list_enrollments": {}, "get_enrollment": {"enrollment_id": "e1"},
    "list_certificates": {}, "get_certificate": {"certificate_id": "cert1"},
    "get_course_analytics": {"course_id": "c1"}, "list_course_ratings": {"course_id": "c1"},
    "update_enrollments": {"items": []},
    "complete_enrollments": {"send_notifications": False, "items": []},
    "bulk_enroll": {"published_course_id": "pc1", "emails": []},
    "list_students": {}, "get_student": {"student_id": "s1"},
    "create_students": {"items": []}, "update_students": {"items": []},
    "anonymize_student": {"student_id": "s1"},
    "deactivate_student": {"student_id": "s1"},
    "set_student_password": {"student_id": "s1", "password": "x"},
    "send_password_reset": {"student_id": "s1", "domain": "d"},
    "list_groups": {}, "get_group": {"group_id": "g1"},
    "create_groups": {"items": []}, "update_groups": {"items": []},
    "delete_groups": {"group_ids": []},
    "add_group_memberships": {"group_id": "g1", "student_ids": []},
    "remove_group_memberships": {"group_id": "g1", "student_ids": []},
    "list_signup_field_values": {}, "get_signup_field_value": {"signup_field_value_id": "v1"},
    "create_signup_field_values": {"student_id": "s1", "items": []},
    "update_signup_field_values": {"items": []},
    "list_published_courses": {}, "get_published_course": {"published_course_id": "pc1"},
    "publish_courses": {"items": []}, "update_published_courses": {"items": []},
    "delete_published_course": {"published_course_id": "pc1"},
    "unpublish_published_course": {"published_course_id": "pc1"},
    "republish_published_course": {"published_course_id": "pc1"},
    "list_visibility_overrides": {"group_id": "g1"},
    "add_visibility_overrides": {"group_id": "g1", "items": []},
    "remove_visibility_overrides": {"group_id": "g1", "items": []},
    "list_domains": {}, "get_domain": {"domain_id": "d1"},
    "list_web_packages": {}, "get_web_package": {"web_package_id": "wp1"},
    "create_web_packages": {"items": []}, "update_web_packages": {"items": []},
    "delete_web_package": {"web_package_id": "wp1"},
    "register_oauth_client": {"client_name": "c"},
    "list_oauth_clients": {}, "get_oauth_client": {"client_id": "cl1"},
    "create_oauth_client": {"name": "c"},
    "update_oauth_client": {"client_id": "cl1", "changes": {"name": "c"}},
    "deactivate_oauth_client": {"client_id": "cl1"},
    "rotate_oauth_client_secret": {"client_id": "cl1"},
    "list_oauth_scopes": {}, "revoke_refresh_token": {"token": "t"},
    "find_learner": {"email": "a@b.c"},
    "list_learner_progress": {"user_id": "u1"},
    "get_learner_progress": {"user_id": "u1", "published_course_id": "pc1"},
    "list_assets": {}, "get_asset": {"asset_id": "a1"},
    "list_promo_codes": {}, "list_promo_code_pools": {}, "list_offers": {},
    "list_training_credit_codes": {}, "get_purchase": {"purchase_id": "pur1"},
    "list_paths": {}, "get_path": {"path_id": "p1"},
    "list_path_items": {"path_id": "p1"},
    "list_published_paths": {"domain_name": "d"}, "list_course_series": {"domain_name": "d"},
    "list_learner_path_enrollments": {"user_id": "u1"},
}


def test_the_matrix_covers_every_gated_method():
    """If a block adds a Backend method and forgets the matrix, that is a hole."""
    covered = set().union(*EXPECTED_BY_CAPABILITY.values())
    assert covered == set(P._GATES), (
        f"matrix and _GATES disagree: {sorted(covered ^ set(P._GATES))}"
    )


class BothBackends(FakeBackend):
    """A v2 fake that also answers the v1 method names.

    The matrix tests the GATE, not the backend, and `PolicyBackend` refuses before it
    delegates - so what matters here is that every gated name is reachable. Since Block
    11 the gate table covers two APIs, and a v2-only double made every v1 row raise
    AttributeError before the gate could be observed at all.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._v1 = FakeV1Backend()

    def find_learner(self, **kw):
        return self._v1.find_learner(**kw)

    def list_learner_progress(self, **kw):
        return self._v1.list_learner_progress(**kw)

    def get_learner_progress(self, **kw):
        return self._v1.get_learner_progress(**kw)

    def list_assets(self, **kw):
        return self._v1.list_assets(**kw)

    def get_asset(self, **kw):
        return self._v1.get_asset(**kw)

    def list_promo_codes(self, **kw):
        return self._v1.list_promo_codes(**kw)

    def list_promo_code_pools(self, **kw):
        return self._v1.list_promo_code_pools(**kw)

    def list_offers(self, **kw):
        return self._v1.list_offers(**kw)

    def list_training_credit_codes(self, **kw):
        return self._v1.list_training_credit_codes(**kw)

    def get_purchase(self, **kw):
        return self._v1.get_purchase(**kw)

    def list_paths(self, **kw):
        return self._v1.list_paths(**kw)

    def get_path(self, **kw):
        return self._v1.get_path(**kw)

    def list_path_items(self, **kw):
        return self._v1.list_path_items(**kw)

    def list_published_paths(self, **kw):
        return self._v1.list_published_paths(**kw)

    def list_course_series(self, **kw):
        return self._v1.list_course_series(**kw)

    def list_learner_path_enrollments(self, **kw):
        return self._v1.list_learner_path_enrollments(**kw)


def test_one_capability_at_a_time_matrix():
    """Enable exactly one capability; assert precisely which operations become possible."""
    every_method = set().union(*EXPECTED_BY_CAPABILITY.values())
    for cap in P.ALL_CAPABILITIES:
        allowed = EXPECTED_BY_CAPABILITY.get(cap, set())
        pb = P.PolicyBackend(BothBackends(courses=ROWS), P.Policy(frozenset({cap})))
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
