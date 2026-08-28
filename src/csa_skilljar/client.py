"""`SkilljarClient` - the library entry point. The MCP server is one consumer of it."""
from __future__ import annotations

from typing import Any

from . import exceptions as exc
from .backend import Backend
from .policy import Policy, PolicyBackend


class SkilljarClient:
    """Thin, typed surface over the backends.

    TWO backends, and which one answers is fixed per capability (ADR-002): v2 owns every
    capability v2 has, v1 is used only for what v2 lacks. There is no fallback in either
    direction, and no method consults both. The two APIs have incompatible data models -
    JSON:API with opaque cursors against a DRF envelope with page numbers - so a silent
    fallback would hand callers a different shape for the same question depending on
    which backend happened to answer.

    `v1` is optional. Without it the v1-only capabilities raise a typed error naming the
    variable to set, rather than the server refusing to start: a v1 key is not needed to
    use any of the v2 surface.
    """

    def __init__(self, backend: Backend | PolicyBackend,
                 v1: Any | None = None) -> None:
        self._backend = backend
        self._v1 = v1

    @property
    def credentials(self) -> Any | None:
        """The v2 credentials, when the backend has any.

        Exists so `check_access` does not have to reach through
        `client._backend._backend._creds` - which the Block 1 plan flagged as a wart
        with three layers of private attribute access. Returns None for a fake or
        credential-free backend rather than raising, because `check_access` must answer
        when nothing is configured.
        """
        inner = getattr(self._backend, "_backend", self._backend)
        return getattr(inner, "_creds", None)

    def _require_v1(self) -> Any:
        if self._v1 is None:
            raise exc.CredentialsMissing(
                "this capability is served by Skilljar's v1 API, which is not "
                "configured. Set CSA_SKILLJAR_V1_API_KEY in your MCP client "
                "configuration and restart. It is a separate credential from the v2 "
                "client id and secret, and neither substitutes for the other. Call "
                "`check_access` to see what is available.")
        return self._v1

    @property
    def policy(self) -> Policy | None:
        """The active policy, when the backend is policy-wrapped. `None` for a raw backend."""
        return getattr(self._backend, "policy", None)

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_courses(title=title, cursor=cursor, page_size=page_size)

    def get_course(self, *, course_id: str) -> dict[str, Any]:
        return self._backend.get_course(course_id=course_id)

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_lessons(
            course_id=course_id, title=title, lesson_type=lesson_type,
            updated_since=updated_since, cursor=cursor, page_size=page_size)

    def get_lesson(self, *, lesson_id: str) -> dict[str, Any]:
        return self._backend.get_lesson(lesson_id=lesson_id)

    def create_courses(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_courses(items=items)

    def update_courses(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_courses(items=items)

    def create_lessons(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_lessons(items=items)

    def update_lessons(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_lessons(items=items)

    def list_quizzes(self, *, name: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_quizzes(name=name, updated_since=updated_since,
                                          cursor=cursor, page_size=page_size)

    def get_quiz(self, *, quiz_id: str) -> dict[str, Any]:
        return self._backend.get_quiz(quiz_id=quiz_id)

    def create_quizzes(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_quizzes(items=items)

    def update_quizzes(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_quizzes(items=items)

    def delete_quizzes(self, *, quiz_ids: list[str]) -> dict[str, Any]:
        return self._backend.delete_quizzes(quiz_ids=quiz_ids)

    def list_questions(self, *, quiz_id: str | None = None,
                       question_bank_id: str | None = None, cursor: str | None = None,
                       page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_questions(
            quiz_id=quiz_id, question_bank_id=question_bank_id,
            cursor=cursor, page_size=page_size)

    def get_question(self, *, question_id: str) -> dict[str, Any]:
        return self._backend.get_question(question_id=question_id)

    def create_questions(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_questions(items=items)

    def update_questions(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_questions(items=items)

    def delete_questions(self, *, question_ids: list[str]) -> dict[str, Any]:
        return self._backend.delete_questions(question_ids=question_ids)

    def list_question_banks(self, *, name: str | None = None,
                            updated_since: str | None = None, cursor: str | None = None,
                            page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_question_banks(
            name=name, updated_since=updated_since, cursor=cursor, page_size=page_size)

    def get_question_bank(self, *, bank_id: str) -> dict[str, Any]:
        return self._backend.get_question_bank(bank_id=bank_id)

    def create_question_banks(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_question_banks(items=items)

    def update_question_banks(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_question_banks(items=items)

    def delete_question_banks(self, *, bank_ids: list[str]) -> dict[str, Any]:
        return self._backend.delete_question_banks(bank_ids=bank_ids)

    def list_bank_assignments(self, *, quiz_id: str) -> dict[str, Any]:
        return self._backend.list_bank_assignments(quiz_id=quiz_id)

    def bind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.bind_banks(quiz_id=quiz_id, items=items)

    def update_bank_assignments(self, *, quiz_id: str,
                                items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_bank_assignments(quiz_id=quiz_id, items=items)

    def unbind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.unbind_banks(quiz_id=quiz_id, items=items)

    def list_enrollments(self, **kw: Any) -> dict[str, Any]:
        return self._backend.list_enrollments(**kw)

    def get_enrollment(self, *, enrollment_id: str,
                       include: str | None = None) -> dict[str, Any]:
        return self._backend.get_enrollment(enrollment_id=enrollment_id, include=include)

    def update_enrollments(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_enrollments(items=items)

    def complete_enrollments(self, *, send_notifications: bool,
                             items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.complete_enrollments(
            send_notifications=send_notifications, items=items)

    def bulk_enroll(self, *, published_course_id: str, emails: list[str],
                    expires_at: str | None = None) -> dict[str, Any]:
        return self._backend.bulk_enroll(published_course_id=published_course_id,
                                         emails=emails, expires_at=expires_at)

    def list_certificates(self, **kw: Any) -> dict[str, Any]:
        return self._backend.list_certificates(**kw)

    def get_certificate(self, *, certificate_id: str) -> dict[str, Any]:
        return self._backend.get_certificate(certificate_id=certificate_id)

    def get_course_analytics(self, *, course_id: str,
                             domains: str | None = None) -> dict[str, Any]:
        return self._backend.get_course_analytics(course_id=course_id, domains=domains)

    def list_course_ratings(self, *, course_id: str,
                            student_id: str | None = None) -> dict[str, Any]:
        return self._backend.list_course_ratings(course_id=course_id, student_id=student_id)

    def list_students(self, **kw: Any) -> dict[str, Any]:
        return self._backend.list_students(**kw)

    def get_student(self, *, student_id: str) -> dict[str, Any]:
        return self._backend.get_student(student_id=student_id)

    def create_students(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_students(items=items)

    def update_students(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_students(items=items)

    def anonymize_student(self, *, student_id: str) -> dict[str, Any]:
        return self._backend.anonymize_student(student_id=student_id)

    def deactivate_student(self, *, student_id: str) -> dict[str, Any]:
        return self._backend.deactivate_student(student_id=student_id)

    def set_student_password(self, *, student_id: str, password: str) -> dict[str, Any]:
        return self._backend.set_student_password(student_id=student_id, password=password)

    def send_password_reset(self, *, student_id: str, domain: str) -> dict[str, Any]:
        return self._backend.send_password_reset(student_id=student_id, domain=domain)

    def list_groups(self, *, name: str | None = None, category_id: str | None = None,
                    cursor: str | None = None,
                    page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_groups(name=name, category_id=category_id,
                                         cursor=cursor, page_size=page_size)

    def get_group(self, *, group_id: str) -> dict[str, Any]:
        return self._backend.get_group(group_id=group_id)

    def create_groups(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_groups(items=items)

    def update_groups(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_groups(items=items)

    def delete_groups(self, *, group_ids: list[str]) -> dict[str, Any]:
        return self._backend.delete_groups(group_ids=group_ids)

    def add_group_memberships(self, *, group_id: str,
                              student_ids: list[str]) -> dict[str, Any]:
        return self._backend.add_group_memberships(group_id=group_id,
                                                   student_ids=student_ids)

    def remove_group_memberships(self, *, group_id: str,
                                 student_ids: list[str]) -> dict[str, Any]:
        return self._backend.remove_group_memberships(group_id=group_id,
                                                      student_ids=student_ids)

    def list_signup_field_values(self, *, student_id: str | None = None,
                                 signup_field_id: str | None = None,
                                 domains: str | None = None, cursor: str | None = None,
                                 page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_signup_field_values(
            student_id=student_id, signup_field_id=signup_field_id, domains=domains,
            cursor=cursor, page_size=page_size)

    def get_signup_field_value(self, *, signup_field_value_id: str) -> dict[str, Any]:
        return self._backend.get_signup_field_value(
            signup_field_value_id=signup_field_value_id)

    def create_signup_field_values(self, *, student_id: str,
                                   items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_signup_field_values(student_id=student_id,
                                                        items=items)

    def update_signup_field_values(self, *,
                                   items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_signup_field_values(items=items)

    def list_published_courses(self, *, course_id: str | None = None,
                               domain_id: str | None = None, live: bool | None = None,
                               include: str | None = None, cursor: str | None = None,
                               page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_published_courses(
            course_id=course_id, domain_id=domain_id, live=live, include=include,
            cursor=cursor, page_size=page_size)

    def get_published_course(self, *, published_course_id: str) -> dict[str, Any]:
        return self._backend.get_published_course(
            published_course_id=published_course_id)

    def publish_courses(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.publish_courses(items=items)

    def update_published_courses(self, *,
                                 items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_published_courses(items=items)

    def delete_published_course(self, *, published_course_id: str) -> dict[str, Any]:
        return self._backend.delete_published_course(
            published_course_id=published_course_id)

    def unpublish_published_course(self, *,
                                   published_course_id: str) -> dict[str, Any]:
        return self._backend.unpublish_published_course(
            published_course_id=published_course_id)

    def republish_published_course(self, *,
                                   published_course_id: str) -> dict[str, Any]:
        return self._backend.republish_published_course(
            published_course_id=published_course_id)

    def list_visibility_overrides(self, *, group_id: str, is_visible: bool | None = None,
                                  published_course_id: str | None = None,
                                  cursor: str | None = None,
                                  page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_visibility_overrides(
            group_id=group_id, is_visible=is_visible,
            published_course_id=published_course_id, cursor=cursor, page_size=page_size)

    def add_visibility_overrides(self, *, group_id: str,
                                 items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.add_visibility_overrides(group_id=group_id, items=items)

    def remove_visibility_overrides(self, *, group_id: str,
                                    items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.remove_visibility_overrides(group_id=group_id, items=items)

    def list_domains(self, *, access: str | None = None, name: str | None = None,
                     include: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_domains(access=access, name=name, include=include,
                                          cursor=cursor, page_size=page_size)

    def get_domain(self, *, domain_id: str) -> dict[str, Any]:
        return self._backend.get_domain(domain_id=domain_id)

    def list_web_packages(self) -> dict[str, Any]:
        return self._backend.list_web_packages()

    def get_web_package(self, *, web_package_id: str) -> dict[str, Any]:
        return self._backend.get_web_package(web_package_id=web_package_id)

    def create_web_packages(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.create_web_packages(items=items)

    def update_web_packages(self, *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._backend.update_web_packages(items=items)

    def delete_web_package(self, *, web_package_id: str) -> dict[str, Any]:
        return self._backend.delete_web_package(web_package_id=web_package_id)

    def register_oauth_client(self, *, client_name: str,
                              redirect_uris: list[str] | None = None,
                              grant_types: list[str] | None = None,
                              scope: str | None = None,
                              token_endpoint_auth_method: str = "client_secret_post",
                              resource: str = "") -> dict[str, Any]:
        return self._backend.register_oauth_client(
            client_name=client_name, redirect_uris=redirect_uris,
            grant_types=grant_types, scope=scope,
            token_endpoint_auth_method=token_endpoint_auth_method, resource=resource)

    def list_oauth_clients(self) -> dict[str, Any]:
        return self._backend.list_oauth_clients()

    def get_oauth_client(self, *, client_id: str) -> dict[str, Any]:
        return self._backend.get_oauth_client(client_id=client_id)

    def create_oauth_client(self, *, name: str, description: str | None = None,
                            scope_codenames: list[str] | None = None,
                            scope_preset: str | None = None,
                            ip_allowlist: list[str] | None = None) -> dict[str, Any]:
        return self._backend.create_oauth_client(
            name=name, description=description, scope_codenames=scope_codenames,
            scope_preset=scope_preset, ip_allowlist=ip_allowlist)

    def update_oauth_client(self, *, client_id: str,
                            changes: dict[str, Any]) -> dict[str, Any]:
        return self._backend.update_oauth_client(client_id=client_id, changes=changes)

    def deactivate_oauth_client(self, *, client_id: str) -> dict[str, Any]:
        return self._backend.deactivate_oauth_client(client_id=client_id)

    def rotate_oauth_client_secret(self, *, client_id: str) -> dict[str, Any]:
        return self._backend.rotate_oauth_client_secret(client_id=client_id)

    def list_oauth_scopes(self) -> dict[str, Any]:
        return self._backend.list_oauth_scopes()

    def revoke_refresh_token(self, *, token: str,
                             token_type_hint: str | None = None) -> dict[str, Any]:
        return self._backend.revoke_refresh_token(token=token,
                                                  token_type_hint=token_type_hint)

    # --- v1-only capabilities. v2 has no equivalent; see ADR-002. ----------------------

    def find_learner(self, *, email: str) -> dict[str, Any]:
        return self._require_v1().find_learner(email=email)

    def list_learner_progress(self, *, user_id: str,
                              page: int | None = None) -> dict[str, Any]:
        return self._require_v1().list_learner_progress(user_id=user_id, page=page)

    def get_learner_progress(self, *, user_id: str,
                             published_course_id: str) -> dict[str, Any]:
        return self._require_v1().get_learner_progress(
            user_id=user_id, published_course_id=published_course_id)

    def list_assets(self, *, page: int | None = None) -> dict[str, Any]:
        return self._require_v1().list_assets(page=page)

    def get_asset(self, *, asset_id: str) -> dict[str, Any]:
        return self._require_v1().get_asset(asset_id=asset_id)
