"""`SkilljarClient` - the library entry point. The MCP server is one consumer of it."""
from __future__ import annotations

from typing import Any

from .backend import Backend
from .policy import Policy, PolicyBackend


class SkilljarClient:
    """Thin, typed surface over a (policy-wrapped) Backend."""

    def __init__(self, backend: Backend | PolicyBackend) -> None:
        self._backend = backend

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
