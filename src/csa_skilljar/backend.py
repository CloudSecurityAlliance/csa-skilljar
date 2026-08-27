"""The seam. `Backend` is the protocol; `PolicyBackend` wraps it; `V2Backend` is real.

Every method takes keyword-only arguments so `PolicyBackend` can wrap uniformly, and
returns the raw v2 JSON:API envelope - shaping belongs to the delivery layer, not here.
"""
from __future__ import annotations

import copy
from typing import Any, Protocol, runtime_checkable

import httpx

from . import exceptions as exc
from .auth import V2Credentials
from .scopes import is_known_operation, scopes_for

Envelope = dict[str, Any]


def parse_batch(envelope: Envelope) -> dict[str, Any]:
    """Split a 207 batch envelope into succeeded and failed items.

    v2 collection writes return per-item results rather than one status for the whole
    request. Preserving that split is the point: a caller told only "the batch failed"
    cannot tell which forty-nine rows landed.

    The `succeeded + failed == total` invariant is CHECKED, not trusted. Skilljar
    enforces it server-side, so a mismatch means we are misreading the envelope - and
    reporting a confidently wrong count is worse than raising.
    """
    summary = envelope.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("batch response carried no summary; this is not a 207 envelope")
    total = int(summary.get("total", 0))
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in envelope.get("data", []):
        if item.get("status") == "error":
            failed.append({
                "code": item.get("code", "unknown"),
                "detail": item.get("detail", ""),
                "pointer": (item.get("source") or {}).get("pointer", ""),
            })
        else:
            succeeded.append(item)
    if len(succeeded) + len(failed) != total:
        raise ValueError(
            f"batch summary disagrees with its own data: summary total={total} but "
            f"{len(succeeded)} succeeded + {len(failed)} failed were present")
    return {"succeeded": succeeded, "failed": failed, "total": total}


@runtime_checkable
class Backend(Protocol):
    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope: ...

    def get_course(self, *, course_id: str) -> Envelope: ...

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope: ...

    def get_lesson(self, *, lesson_id: str) -> Envelope: ...

    def create_courses(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_courses(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def create_lessons(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_lessons(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def list_quizzes(self, *, name: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope: ...

    def get_quiz(self, *, quiz_id: str) -> Envelope: ...

    def create_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def delete_quizzes(self, *, quiz_ids: list[str]) -> Envelope: ...

    def list_questions(self, *, quiz_id: str | None = None,
                       question_bank_id: str | None = None, cursor: str | None = None,
                       page_size: int | None = None) -> Envelope: ...

    def get_question(self, *, question_id: str) -> Envelope: ...

    def create_questions(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_questions(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def delete_questions(self, *, question_ids: list[str]) -> Envelope: ...

    def list_question_banks(self, *, name: str | None = None,
                            updated_since: str | None = None, cursor: str | None = None,
                            page_size: int | None = None) -> Envelope: ...

    def get_question_bank(self, *, bank_id: str) -> Envelope: ...

    def create_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def delete_question_banks(self, *, bank_ids: list[str]) -> Envelope: ...

    def list_bank_assignments(self, *, quiz_id: str) -> Envelope: ...

    def bind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope: ...

    def update_bank_assignments(self, *, quiz_id: str,
                                items: list[dict[str, Any]]) -> Envelope: ...

    def unbind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope: ...

    def list_enrollments(self, *, active: bool | None = None,
                         completed_gte: str | None = None, completed_lte: str | None = None,
                         enrolled_gte: str | None = None, enrolled_lte: str | None = None,
                         course_id: str | None = None, domains: str | None = None,
                         progress_status: str | None = None,
                         student_email: str | None = None, student_id: str | None = None,
                         include: str | None = None, cursor: str | None = None,
                         page_size: int | None = None) -> Envelope: ...

    def get_enrollment(self, *, enrollment_id: str,
                       include: str | None = None) -> Envelope: ...

    def update_enrollments(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def complete_enrollments(self, *, send_notifications: bool,
                             items: list[dict[str, Any]]) -> Envelope: ...

    def bulk_enroll(self, *, published_course_id: str, emails: list[str],
                    expires_at: str | None = None) -> Envelope: ...

    def list_certificates(self, *, course_id: str | None = None,
                          student_id: str | None = None, domains: str | None = None,
                          issued_gte: str | None = None, issued_lte: str | None = None,
                          status: str = "all", cursor: str | None = None,
                          page_size: int | None = None) -> Envelope: ...

    def get_certificate(self, *, certificate_id: str) -> Envelope: ...

    def get_course_analytics(self, *, course_id: str,
                             domains: str | None = None) -> Envelope: ...

    def list_course_ratings(self, *, course_id: str,
                            student_id: str | None = None) -> Envelope: ...

    def list_students(self, *, email: str | None = None, first_name: str | None = None,
                      last_name: str | None = None, is_inactive: bool | None = None,
                      cursor: str | None = None, page_size: int | None = None) -> Envelope: ...

    def get_student(self, *, student_id: str) -> Envelope: ...

    def create_students(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def update_students(self, *, items: list[dict[str, Any]]) -> Envelope: ...

    def anonymize_student(self, *, student_id: str) -> Envelope: ...

    def deactivate_student(self, *, student_id: str) -> Envelope: ...

    def set_student_password(self, *, student_id: str, password: str) -> Envelope: ...

    def send_password_reset(self, *, student_id: str, domain: str) -> Envelope: ...


class FakeBackend:
    """In-memory double. Powers the entire offline suite - no network, no credentials.

    Deliberately implements the *shape* of v2's cursor pagination, including the
    `has_more` / `next_cursor` pair, because code that only ever sees a single page
    is code that has never exercised paging.
    """

    def __init__(self, courses: list[dict[str, Any]] | None = None,
                 lessons: list[dict[str, Any]] | None = None,
                 quizzes: list[dict[str, Any]] | None = None,
                 questions: list[dict[str, Any]] | None = None,
                 question_banks: list[dict[str, Any]] | None = None,
                 enrollments: list[dict[str, Any]] | None = None,
                 certificates: list[dict[str, Any]] | None = None,
                 course_ratings: list[dict[str, Any]] | None = None,
                 students: list[dict[str, Any]] | None = None) -> None:
        # DEEP copy. `list(rows)` copies the list but shares every row dict, so an
        # update through the fake silently rewrites the caller's fixture - which it did:
        # a module-level ROWS constant was mutated to "Renamed" by one test and broke a
        # different one. A double that mutates its input is a trap, not a double.
        self._courses = copy.deepcopy(list(courses or []))
        self._lessons = copy.deepcopy(list(lessons or []))
        self._quizzes = copy.deepcopy(list(quizzes or []))
        self._questions = copy.deepcopy(list(questions or []))
        self._banks = copy.deepcopy(list(question_banks or []))
        # (quiz_id, question_bank_id) -> assignment attributes. A join row keyed by a
        # natural key, not by an id of its own.
        self._assignments: dict[tuple[str, str], dict[str, Any]] = {}
        self._enrollments = copy.deepcopy(list(enrollments or []))
        self._certificates = copy.deepcopy(list(certificates or []))
        self._ratings = copy.deepcopy(list(course_ratings or []))
        self._students = copy.deepcopy(list(students or []))

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        rows = self._courses
        if title is not None:
            needle = title.lower()
            rows = [c for c in rows if needle in c.get("attributes", {}).get("title", "").lower()]
        return self._page(rows, cursor, page_size, "/v2/courses/")

    def _page(self, rows: list[dict[str, Any]], cursor: str | None,
              page_size: int | None, self_link: str) -> Envelope:
        """v2's cursor pagination shape, shared by every listing.

        The cursor is an integer index here and an opaque token upstream - which is
        exactly why `tests/integration/` has to prove real pagination separately.
        """
        start = int(cursor) if cursor else 0
        size = page_size or 25
        page = rows[start:start + size]
        nxt = start + size
        more = nxt < len(rows)
        return {"data": page, "meta": {"page_size": size},
                "links": {"self": self_link, "next": None, "prev": None},
                "has_more": more, "next_cursor": str(nxt) if more else None}

    def get_course(self, *, course_id: str) -> Envelope:
        for row in self._courses:
            if row.get("id") == course_id:
                return {"data": row}
        raise exc.NotFoundError(f"no course with id {course_id}")

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        rows = self._lessons
        if course_id is not None:
            rows = [x for x in rows if x.get("attributes", {}).get("course_id") == course_id]
        if title is not None:
            # EXACT match, case-insensitive - unlike course titles, which match partially.
            rows = [x for x in rows
                    if x.get("attributes", {}).get("title", "").lower() == title.lower()]
        if lesson_type is not None:
            rows = [x for x in rows if x.get("attributes", {}).get("type") == lesson_type]
        if updated_since is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("modified_at", "") >= updated_since]
        return self._page(rows, cursor, page_size, "/v2/lessons/")

    def get_lesson(self, *, lesson_id: str) -> Envelope:
        for row in self._lessons:
            if row.get("id") == lesson_id:
                return {"data": row}
        raise exc.NotFoundError(f"no lesson with id {lesson_id}")

    @staticmethod
    def _batch(data: list[dict[str, Any]]) -> Envelope:
        failed = sum(1 for d in data if d.get("status") == "error")
        return {"data": data, "summary": {"total": len(data),
                                          "succeeded": len(data) - failed, "failed": failed}}

    # Emails the fake will resolve to an organization membership. Anything else is a
    # per-item failure, matching the real service: created_by_email is resolved against
    # active OrganizationMemberships, and an unresolvable one fails that ROW rather than
    # the request - unlike a schema violation, which rejects everything.
    KNOWN_MEMBERS = frozenset({"author@example.org"})

    def create_courses(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            title = attrs.get("title", "")
            if not title or len(title) > 500:
                data.append({"status": "error", "code": "validation_error",
                             "detail": "title is required and must be 1..500 characters",
                             "source": {"pointer": f"/data/{i}/attributes/title"}})
                continue
            email = attrs.get("created_by_email")
            if email and email not in self.KNOWN_MEMBERS:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"{email} is not an active member of this organization",
                             "source": {"pointer": f"/data/{i}/attributes/created_by_email"}})
                continue
            new_id = f"c{len(self._courses) + 1}"
            self._courses.append({"type": "courses", "id": new_id,
                                  "attributes": dict(attrs)})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_courses(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            cid = item.get("id")
            row = next((r for r in self._courses if r.get("id") == cid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no course with id {cid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            # PARTIAL update: an omitted field is preserved, never cleared.
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": cid})
        return self._batch(data)

    def create_lessons(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            if not attrs.get("course_id"):
                data.append({"status": "error", "code": "not_found",
                             "detail": "course_id is required",
                             "source": {"pointer": f"/data/{i}/attributes/course_id"}})
                continue
            new_id = f"l{len(self._lessons) + 1}"
            stored = dict(attrs)
            stored.setdefault("order", (max(
                (x.get("attributes", {}).get("order", 0) for x in self._lessons), default=0) + 10))
            self._lessons.append({"type": "lessons", "id": new_id, "attributes": stored})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_lessons(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            lid = item.get("id")
            row = next((r for r in self._lessons if r.get("id") == lid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no lesson with id {lid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            # content_items is a TRI-STATE: omitted leaves children alone, present
            # replaces them, present-and-empty deletes them all. The delivery layer
            # gates the destructive case behind an explicit flag; here it is applied
            # exactly as sent, because that is what the API does.
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": lid})
        return self._batch(data)

    def list_quizzes(self, *, name: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        rows = self._quizzes
        if name is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("name", "").lower() == name.lower()]
        if updated_since is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("modified_at", "") >= updated_since]
        return self._page(rows, cursor, page_size, "/v2/quizzes/")

    def get_quiz(self, *, quiz_id: str) -> Envelope:
        for row in self._quizzes:
            if row.get("id") == quiz_id:
                return {"data": row}
        raise exc.NotFoundError(f"no quiz with id {quiz_id}")

    def create_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            if not attrs.get("name"):
                data.append({"status": "error", "code": "validation_error",
                             "detail": "name is required",
                             "source": {"pointer": f"/data/{i}/attributes/name"}})
                continue
            new_id = f"q{len(self._quizzes) + 1}"
            self._quizzes.append({"type": "quizzes", "id": new_id, "attributes": dict(attrs)})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            qid = item.get("id")
            row = next((r for r in self._quizzes if r.get("id") == qid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no quiz with id {qid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": qid})
        return self._batch(data)

    def delete_quizzes(self, *, quiz_ids: list[str]) -> Envelope:
        """Soft-delete. The quiz's OWN questions go with it; shared banks do not."""
        data: list[dict[str, Any]] = []
        for i, qid in enumerate(quiz_ids):
            row = next((r for r in self._quizzes if r.get("id") == qid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no quiz with id {qid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            self._quizzes.remove(row)
            # A quiz owns only questions where question.quiz == quiz. Bank-owned
            # questions survive - that is the cascade rule from the captured registry.
            self._questions = [q for q in self._questions
                               if q.get("attributes", {}).get("quiz_id") != qid]
            data.append({"status": "deleted", "id": qid})
        return self._batch(data)

    def list_questions(self, *, quiz_id: str | None = None,
                       question_bank_id: str | None = None, cursor: str | None = None,
                       page_size: int | None = None) -> Envelope:
        rows = self._questions
        if quiz_id is not None:
            rows = [x for x in rows if x.get("attributes", {}).get("quiz_id") == quiz_id]
        if question_bank_id is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("question_bank_id") == question_bank_id]
        return self._page(rows, cursor, page_size, "/v2/questions/")

    def get_question(self, *, question_id: str) -> Envelope:
        for row in self._questions:
            if row.get("id") == question_id:
                return {"data": row}
        raise exc.NotFoundError(f"no question with id {question_id}")

    def create_questions(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            parent = attrs.get("quiz_id") or attrs.get("question_bank_id")
            if not parent:
                data.append({"status": "error", "code": "not_found",
                             "detail": "a question needs a quiz_id or a question_bank_id",
                             "source": {"pointer": f"/data/{i}"}})
                continue
            stored = dict(attrs)
            # The service assigns order and per-answer order; it never accepts them.
            stored["order"] = (max((q.get("attributes", {}).get("order", 0)
                                    for q in self._questions), default=0) + 10)
            answers = [dict(a) for a in stored.get("answers", [])]
            if stored.get("question_type") == "FILL_IN_THE_BLANK":
                # Quirk from the captured registry: `correct` is accepted for a uniform
                # wire shape and then FORCED True for this type regardless.
                for a in answers:
                    a["correct"] = True
            for idx, a in enumerate(answers):
                a["order"] = idx * 10
            stored["answers"] = answers
            new_id = f"qu{len(self._questions) + 1}"
            self._questions.append({"type": "questions", "id": new_id, "attributes": stored})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_questions(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            qid = item.get("id")
            row = next((r for r in self._questions if r.get("id") == qid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no question with id {qid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            stored_type = row.get("attributes", {}).get("question_type")
            # Cross-state validation: a flag conflicting with the STORED type is a
            # PER-ITEM validation_error, not a document-level 422 - the schema cannot
            # see the stored type, so this can only happen here.
            if "case_sensitive" in item and stored_type != "FILL_IN_THE_BLANK":
                data.append({"status": "error", "code": "validation_error",
                             "detail": f"case_sensitive is only valid on FILL_IN_THE_BLANK "
                                       f"questions; this one is {stored_type}",
                             "source": {"pointer": f"/data/{i}/attributes/case_sensitive"}})
                continue
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": qid})
        return self._batch(data)

    def delete_questions(self, *, question_ids: list[str]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, qid in enumerate(question_ids):
            row = next((r for r in self._questions if r.get("id") == qid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no question with id {qid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            self._questions.remove(row)
            data.append({"status": "deleted", "id": qid})
        return self._batch(data)

    # --- question banks ------------------------------------------------------------

    def list_question_banks(self, *, name: str | None = None,
                            updated_since: str | None = None, cursor: str | None = None,
                            page_size: int | None = None) -> Envelope:
        rows = self._banks
        if name is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("name", "").lower() == name.lower()]
        if updated_since is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("modified_at", "") >= updated_since]
        return self._page(rows, cursor, page_size, "/v2/question-banks/")

    def get_question_bank(self, *, bank_id: str) -> Envelope:
        for row in self._banks:
            if row.get("id") == bank_id:
                return {"data": row}
        raise exc.NotFoundError(f"no question bank with id {bank_id}")

    def create_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            if not attrs.get("name"):
                data.append({"status": "error", "code": "validation_error",
                             "detail": "name is required",
                             "source": {"pointer": f"/data/{i}/attributes/name"}})
                continue
            new_id = f"b{len(self._banks) + 1}"
            self._banks.append({"type": "question-banks", "id": new_id,
                                "attributes": dict(attrs)})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            bid = item.get("id")
            row = next((r for r in self._banks if r.get("id") == bid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no question bank with id {bid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": bid})
        return self._batch(data)

    def delete_question_banks(self, *, bank_ids: list[str]) -> Envelope:
        """Soft-deletes the bank's questions, HARD-removes its assignments, then the
        bank. Quizzes that referenced it stay alive - only their assignment rows go."""
        data: list[dict[str, Any]] = []
        for i, bid in enumerate(bank_ids):
            row = next((r for r in self._banks if r.get("id") == bid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no question bank with id {bid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            self._banks.remove(row)
            self._questions = [q for q in self._questions
                               if q.get("attributes", {}).get("question_bank_id") != bid]
            self._assignments = {k: v for k, v in self._assignments.items() if k[1] != bid}
            data.append({"status": "deleted", "id": bid})
        return self._batch(data)

    # --- quiz <-> bank assignments ---------------------------------------------------

    def _require_quiz(self, quiz_id: str) -> None:
        """Resolved once up front: a bad quiz is a document-level 404, not per-item."""
        if not any(q.get("id") == quiz_id for q in self._quizzes):
            raise exc.NotFoundError(f"no quiz with id {quiz_id}")

    def list_bank_assignments(self, *, quiz_id: str) -> Envelope:
        self._require_quiz(quiz_id)
        rows: list[dict[str, Any]] = [
            {"type": "question-bank-assignments",
             "attributes": {"question_bank_id": bank, **attrs}}
            for (q, bank), attrs in self._assignments.items() if q == quiz_id]
        rows.sort(key=lambda r: int(r["attributes"].get("order", 0)))
        return {"data": rows}

    def bind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope:
        """update_or_create on the natural key.

        Re-binding is an IDEMPOTENT PARTIAL UPDATE: only supplied fields are written, an
        omitted field keeps its stored value, and an omitted `order` is NOT re-derived.
        A create-or-replace here silently reorders someone's exam.
        """
        self._require_quiz(quiz_id)
        data: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i, attrs in enumerate(items):
            bank = str(attrs.get("question_bank_id"))
            if bank in seen:
                data.append({"status": "error", "code": "duplicate_in_batch",
                             "detail": f"{bank} appears earlier in this batch",
                             "source": {"pointer": f"/data/{i}/attributes/question_bank_id"}})
                continue
            seen.add(bank)
            if not any(b.get("id") == bank for b in self._banks):
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no question bank with id {bank}",
                             "source": {"pointer": f"/data/{i}/attributes/question_bank_id"}})
                continue
            key = (quiz_id, bank)
            supplied = {k: v for k, v in attrs.items() if k != "question_bank_id"}
            if key in self._assignments:
                self._assignments[key].update(supplied)      # PARTIAL: merge, never replace
            else:
                existing = [a.get("order", 0) for (q, _), a in self._assignments.items()
                            if q == quiz_id]
                defaults = {"order": max(existing, default=0) + 10,
                            "randomize_questions": False, "limit_question_count": 0}
                self._assignments[key] = {**defaults, **supplied}
            data.append({"status": "bound", "id": bank})
        return self._batch(data)

    def update_bank_assignments(self, *, quiz_id: str,
                                items: list[dict[str, Any]]) -> Envelope:
        self._require_quiz(quiz_id)
        data: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i, attrs in enumerate(items):
            bank = str(attrs.get("question_bank_id"))
            if bank in seen:
                data.append({"status": "error", "code": "duplicate_in_batch",
                             "detail": f"{bank} appears earlier in this batch",
                             "source": {"pointer": f"/data/{i}/attributes/question_bank_id"}})
                continue
            seen.add(bank)
            key = (quiz_id, bank)
            if key not in self._assignments:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"{bank} is not assigned to this quiz",
                             "source": {"pointer": f"/data/{i}/attributes/question_bank_id"}})
                continue
            # An empty attribute set is a NO-OP SUCCESS, not an error.
            self._assignments[key].update(
                {k: v for k, v in attrs.items() if k != "question_bank_id"})
            data.append({"status": "updated", "id": bank})
        return self._batch(data)

    def unbind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope:
        """HARD delete - QuestionBankAssignment is not a soft-deletion model."""
        self._require_quiz(quiz_id)
        data: list[dict[str, Any]] = []
        for i, attrs in enumerate(items):
            bank = str(attrs.get("question_bank_id"))
            key = (quiz_id, bank)
            if key not in self._assignments:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"{bank} is not assigned to this quiz",
                             "source": {"pointer": f"/data/{i}/attributes/question_bank_id"}})
                continue
            del self._assignments[key]
            data.append({"status": "deleted", "id": bank})
        return self._batch(data)

    # --- enrolment and reporting -----------------------------------------------------

    def list_enrollments(self, *, active: bool | None = None,
                         completed_gte: str | None = None, completed_lte: str | None = None,
                         enrolled_gte: str | None = None, enrolled_lte: str | None = None,
                         course_id: str | None = None, domains: str | None = None,
                         progress_status: str | None = None,
                         student_email: str | None = None, student_id: str | None = None,
                         include: str | None = None, cursor: str | None = None,
                         page_size: int | None = None) -> Envelope:
        rows = self._enrollments
        def attr(r: dict[str, Any], k: str) -> Any:
            return r.get("attributes", {}).get(k)
        if active is not None:
            rows = [r for r in rows if attr(r, "active") is active]
        if progress_status is not None:
            wanted = {s.strip() for s in progress_status.split(",")}
            rows = [r for r in rows if attr(r, "progress_status") in wanted]
        if domains is not None:
            wanted = {s.strip() for s in domains.split(",")}
            rows = [r for r in rows if attr(r, "domain_name") in wanted]
        for key, bound, op in (("completed_at", completed_gte, "ge"),
                               ("completed_at", completed_lte, "le"),
                               ("enrolled_at", enrolled_gte, "ge"),
                               ("enrolled_at", enrolled_lte, "le")):
            if bound is None:
                continue
            rows = [r for r in rows if attr(r, key) and
                    ((attr(r, key) >= bound) if op == "ge" else (attr(r, key) <= bound))]
        return self._page(rows, cursor, page_size, "/v2/enrollments/")

    def get_enrollment(self, *, enrollment_id: str,
                       include: str | None = None) -> Envelope:
        for row in self._enrollments:
            if row.get("id") == enrollment_id:
                return {"data": row}
        raise exc.NotFoundError(f"no enrollment with id {enrollment_id}")

    def update_enrollments(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            eid = item.get("id")
            row = next((r for r in self._enrollments if r.get("id") == eid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no enrollment with id {eid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": eid})
        return self._batch(data)

    def complete_enrollments(self, *, send_notifications: bool,
                             items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            eid = item.get("id")
            row = next((r for r in self._enrollments if r.get("id") == eid), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": f"no enrollment with id {eid}",
                             "source": {"pointer": f"/data/{i}/id"}})
                continue
            row["attributes"].update({k: v for k, v in item.items() if k != "id"})
            data.append({"status": "updated", "id": eid,
                         "notified": bool(send_notifications)})
        return self._batch(data)

    def bulk_enroll(self, *, published_course_id: str, emails: list[str],
                    expires_at: str | None = None) -> Envelope:
        """Hybrid envelope: the course and expiry are shared, emails are per-row."""
        data: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i, raw in enumerate(emails):
            email = str(raw).lower()          # normalised server-side
            if email in seen:
                data.append({"status": "error", "code": "duplicate_in_batch",
                             "detail": f"{email} appears earlier in this batch",
                             "source": {"pointer": f"/data/{i}/attributes/email"}})
                continue
            seen.add(email)
            new_id = f"e{len(self._enrollments) + 1}"
            attrs = {"active": True, "progress_status": "not_started", "email": email,
                     "published_course_id": published_course_id}
            if expires_at:
                attrs["expires_at"] = expires_at
            self._enrollments.append({"type": "enrollments", "id": new_id,
                                      "attributes": attrs})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def list_certificates(self, *, course_id: str | None = None,
                          student_id: str | None = None, domains: str | None = None,
                          issued_gte: str | None = None, issued_lte: str | None = None,
                          status: str = "all", cursor: str | None = None,
                          page_size: int | None = None) -> Envelope:
        rows = self._certificates
        if status != "all":
            rows = [r for r in rows if r.get("attributes", {}).get("status") == status]
        return self._page(rows, cursor, page_size, "/v2/certificates/")

    def get_certificate(self, *, certificate_id: str) -> Envelope:
        for row in self._certificates:
            if row.get("id") == certificate_id:
                return {"data": row}
        raise exc.NotFoundError(f"no certificate with id {certificate_id}")

    def get_course_analytics(self, *, course_id: str,
                             domains: str | None = None) -> Envelope:
        return {"data": {"type": "course-analytics", "id": course_id,
                         "attributes": {"enrollment_count": len(self._enrollments),
                                        "average_rating": 5.0}}}

    def list_course_ratings(self, *, course_id: str,
                            student_id: str | None = None) -> Envelope:
        return {"data": list(self._ratings)}

    # --- students --------------------------------------------------------------------

    def list_students(self, *, email: str | None = None, first_name: str | None = None,
                      last_name: str | None = None, is_inactive: bool | None = None,
                      cursor: str | None = None, page_size: int | None = None) -> Envelope:
        rows = self._students
        def attr(r: dict[str, Any], k: str) -> Any:
            return r.get("attributes", {}).get(k)
        if email is not None:
            rows = [r for r in rows if str(attr(r, "email") or "").lower() == email.lower()]
        if first_name is not None:
            rows = [r for r in rows if attr(r, "first_name") == first_name]
        if last_name is not None:
            rows = [r for r in rows if attr(r, "last_name") == last_name]
        if is_inactive is not None:
            rows = [r for r in rows if bool(attr(r, "is_inactive")) is is_inactive]
        return self._page(rows, cursor, page_size, "/v2/students/")

    def get_student(self, *, student_id: str) -> Envelope:
        for row in self._students:
            if row.get("id") == student_id:
                return {"data": row}
        raise exc.NotFoundError(f"no student with id {student_id}")

    def create_students(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i, attrs in enumerate(items):
            email = str(attrs.get("email", "")).lower()      # normalised on save
            if email in seen:
                data.append({"status": "error", "code": "duplicate_in_batch",
                             "detail": f"{email} appears earlier in this batch",
                             "source": {"pointer": f"/data/{i}/attributes/email"}})
                continue
            seen.add(email)
            new_id = f"s{len(self._students) + 1}"
            self._students.append({"type": "students", "id": new_id,
                                   "attributes": {**attrs, "email": email,
                                                  "is_inactive": False}})
            data.append({"status": "created", "id": new_id})
        return self._batch(data)

    def update_students(self, *, items: list[dict[str, Any]]) -> Envelope:
        data: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            sid, email = item.get("id"), item.get("email")
            if sid:
                row = next((r for r in self._students if r.get("id") == sid), None)
            else:
                row = next((r for r in self._students
                            if str(r.get("attributes", {}).get("email", "")).lower()
                            == str(email).lower()), None)
            if row is None:
                data.append({"status": "error", "code": "not_found",
                             "detail": "no such student in this organization",
                             "source": {"pointer": f"/data/{i}"}})
                continue
            # With an id present, email is a CONFIRMATION, not a value to write.
            if sid and email is not None:
                stored = str(row.get("attributes", {}).get("email", "")).lower()
                if stored != str(email).lower():
                    data.append({"status": "error", "code": "validation_error",
                                 "detail": f"id {sid} is {stored}, not {email}",
                                 "source": {"pointer": f"/data/{i}/attributes/email"}})
                    continue
            row["attributes"].update(
                {k: v for k, v in item.items() if k not in ("id", "email")})
            data.append({"status": "updated", "id": row.get("id")})
        return self._batch(data)

    def anonymize_student(self, *, student_id: str) -> Envelope:
        row = self.get_student(student_id=student_id)["data"]
        row["attributes"] = {"email": f"anonymized-{student_id}@example.invalid",
                             "first_name": "", "last_name": "", "is_inactive": True,
                             "anonymized": True}
        return {"data": row}

    def deactivate_student(self, *, student_id: str) -> Envelope:
        row = self.get_student(student_id=student_id)["data"]
        row["attributes"]["is_inactive"] = True
        return {"data": row}

    def set_student_password(self, *, student_id: str, password: str) -> Envelope:
        self.get_student(student_id=student_id)     # 404s for an unknown id
        return {"data": {"type": "password-sets", "id": student_id}}

    def send_password_reset(self, *, student_id: str, domain: str) -> Envelope:
        self.get_student(student_id=student_id)
        return {"data": {"type": "password-resets", "id": student_id,
                         "attributes": {"domain": domain}}}


class V2Backend:
    """The v2 API. JSON:API envelopes, cursor pagination, per-operation OAuth scopes.

    The scope pre-check runs BEFORE the request: v2 declares `x-required-scope` on every
    operation and the granted scopes are readable from the token, so an impossible call
    is refused locally with an exact remedy and zero network traffic.
    """

    def __init__(self, credentials: V2Credentials, *,
                 base_url: str = "https://api.skilljar.com",
                 http: httpx.Client | None = None) -> None:
        self._creds = credentials; self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)

    def _send(self, method: str, path: str, body: dict[str, Any] | None = None,
              *, template: str | None = None,
              headers: dict[str, str] | None = None) -> Envelope:
        """POST/PATCH/DELETE with the same guarantees as `_get`.

        Deliberately shares `_check_scope` and `_receive` rather than duplicating them:
        the scope pre-check and the "a 200 that is not an envelope is an error" rule
        must not diverge between reads and writes.
        """
        spec_path = template or path
        self._check_scope(method, spec_path)
        try:
            sent = {"Authorization": f"Bearer {self._creds.token()}",
                    "Accept": "application/json", "Content-Type": "application/json"}
            # Extra headers are per-call by design. X-Confirm-Destructive is Skilljar's
            # own gate on irreversible operations; sending it globally because it is
            # easier to thread would silently disarm it for every future one.
            sent.update(headers or {})
            r = self._http.request(method, f"{self._base}{path}", json=body, headers=sent)
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach Skilljar: {e}") from e
        return self._receive(r, spec_path)

    def _check_scope(self, method: str, spec_path: str) -> None:
        # ZD-2: an unknown path must not look like "declared, needs no scope". Without
        # this, a typo silently disables the scope pre-check - a control failing open
        # and saying nothing.
        if not is_known_operation(method, spec_path):
            raise exc.ApiError(
                f"{method} {spec_path} is not a known v2 operation. This is a bug in "
                f"csa-skilljar: the path is absent from the generated scope table. "
                f"Regenerate with scripts/gen_scopes.py if specs/ was refreshed.")
        needed = scopes_for(method, spec_path)
        if needed:
            granted = set(self._creds.granted_scopes())
            if not granted & set(needed):        # any-of semantics
                self._creds.require_scope(needed[0])

    def _receive(self, r: httpx.Response, spec_path: str) -> Envelope:
        if r.status_code == 404:
            raise exc.NotFoundError(f"not found: {spec_path}")
        if r.status_code in (401, 403):
            raise exc.CredentialsRejected(
                "Skilljar rejected the v2 access token. The client may have been deleted "
                "or its credentials rotated. Re-issue the client and restart the server.")
        if r.status_code >= 400:
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {spec_path}",
                status=r.status_code)
        # ZD-2: "responses that technically succeed but look wrong - error on all of it."
        try:
            body = r.json()
        except ValueError as e:
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {spec_path} with a body "
                f"that is not JSON", status=r.status_code) from e
        if not isinstance(body, dict):
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {spec_path} with JSON that "
                f"is not an object (got {type(body).__name__})", status=r.status_code)
        result: Envelope = body
        return result

    def _get(self, path: str, params: dict[str, Any] | None = None,
             *, template: str | None = None) -> Envelope:
        """GET `path`, looking up the required scope under `template`.

        Scope lookup is by literal spec path, so an interpolated `/v2/courses/abc123`
        never matches `/v2/courses/{id}`. Callers with an id in the path pass the
        template separately rather than having the scope pre-check silently skipped.
        """
        spec_path = template or path
        self._check_scope("GET", spec_path)
        try:
            r = self._http.get(
                f"{self._base}{path}",
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers={"Authorization": f"Bearer {self._creds.token()}",
                         "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach Skilljar: {e}") from e
        return self._receive(r, spec_path)

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        return self._get("/v2/courses/", {
            "filter[title]": title,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_course(self, *, course_id: str) -> Envelope:
        return self._get(f"/v2/courses/{course_id}", template="/v2/courses/{id}")

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        return self._get("/v2/lessons/", {
            "filter[course_id]": course_id, "filter[title]": title,
            "filter[type]": lesson_type, "filter[updated_since]": updated_since,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_lesson(self, *, lesson_id: str) -> Envelope:
        return self._get(f"/v2/lessons/{lesson_id}", template="/v2/lessons/{id}")

    def create_courses(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/courses/", {
            "data": [{"type": "courses", "attributes": a} for a in items]})

    def update_courses(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/courses/", {
            "data": [{"type": "courses", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def create_lessons(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/lessons/", {
            "data": [{"type": "lessons", "attributes": a} for a in items]})

    def update_lessons(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/lessons/", {
            "data": [{"type": "lessons", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def list_quizzes(self, *, name: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        return self._get("/v2/quizzes/", {
            "filter[name]": name, "filter[updated_since]": updated_since,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_quiz(self, *, quiz_id: str) -> Envelope:
        return self._get(f"/v2/quizzes/{quiz_id}", template="/v2/quizzes/{id}")

    def create_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/quizzes/", {
            "data": [{"type": "quizzes", "attributes": a} for a in items]})

    def update_quizzes(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/quizzes/", {
            "data": [{"type": "quizzes", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def delete_quizzes(self, *, quiz_ids: list[str]) -> Envelope:
        return self._send("DELETE", "/v2/quizzes/", {
            "data": [{"type": "quizzes", "id": qid} for qid in quiz_ids]})

    def list_questions(self, *, quiz_id: str | None = None,
                       question_bank_id: str | None = None, cursor: str | None = None,
                       page_size: int | None = None) -> Envelope:
        return self._get("/v2/questions/", {
            "filter[quiz_id]": quiz_id, "filter[question_bank_id]": question_bank_id,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_question(self, *, question_id: str) -> Envelope:
        return self._get(f"/v2/questions/{question_id}", template="/v2/questions/{id}")

    def create_questions(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/questions/", {
            "data": [{"type": "questions", "attributes": a} for a in items]})

    def update_questions(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/questions/", {
            "data": [{"type": "questions", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def delete_questions(self, *, question_ids: list[str]) -> Envelope:
        return self._send("DELETE", "/v2/questions/", {
            "data": [{"type": "questions", "id": qid} for qid in question_ids]})

    def list_question_banks(self, *, name: str | None = None,
                            updated_since: str | None = None, cursor: str | None = None,
                            page_size: int | None = None) -> Envelope:
        return self._get("/v2/question-banks/", {
            "filter[name]": name, "filter[updated_since]": updated_since,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_question_bank(self, *, bank_id: str) -> Envelope:
        return self._get(f"/v2/question-banks/{bank_id}",
                         template="/v2/question-banks/{id}")

    def create_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/question-banks/", {
            "data": [{"type": "question-banks", "attributes": a} for a in items]})

    def update_question_banks(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/question-banks/", {
            "data": [{"type": "question-banks", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def delete_question_banks(self, *, bank_ids: list[str]) -> Envelope:
        return self._send("DELETE", "/v2/question-banks/", {
            "data": [{"type": "question-banks", "id": b} for b in bank_ids]})

    def list_bank_assignments(self, *, quiz_id: str) -> Envelope:
        return self._get(f"/v2/quizzes/{quiz_id}/question-banks/",
                         template="/v2/quizzes/{quiz_id}/question-banks/")

    def bind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", f"/v2/quizzes/{quiz_id}/question-banks/",
                          {"data": [{"type": "question-bank-assignments", "attributes": a}
                                    for a in items]},
                          template="/v2/quizzes/{quiz_id}/question-banks/")

    def update_bank_assignments(self, *, quiz_id: str,
                                items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", f"/v2/quizzes/{quiz_id}/question-banks/",
                          {"data": [{"type": "question-bank-assignments", "attributes": a}
                                    for a in items]},
                          template="/v2/quizzes/{quiz_id}/question-banks/")

    def unbind_banks(self, *, quiz_id: str, items: list[dict[str, Any]]) -> Envelope:
        return self._send("DELETE", f"/v2/quizzes/{quiz_id}/question-banks/",
                          {"data": [{"type": "question-bank-assignments", "attributes": a}
                                    for a in items]},
                          template="/v2/quizzes/{quiz_id}/question-banks/")

    def list_enrollments(self, *, active: bool | None = None,
                         completed_gte: str | None = None, completed_lte: str | None = None,
                         enrolled_gte: str | None = None, enrolled_lte: str | None = None,
                         course_id: str | None = None, domains: str | None = None,
                         progress_status: str | None = None,
                         student_email: str | None = None, student_id: str | None = None,
                         include: str | None = None, cursor: str | None = None,
                         page_size: int | None = None) -> Envelope:
        return self._get("/v2/enrollments/", {
            "filter[active]": None if active is None else str(active).lower(),
            "filter[completed_gte]": completed_gte, "filter[completed_lte]": completed_lte,
            "filter[enrolled_gte]": enrolled_gte, "filter[enrolled_lte]": enrolled_lte,
            "filter[course.id]": course_id, "filter[domains]": domains,
            "filter[progress_status]": progress_status,
            "filter[student.email]": student_email, "filter[student.id]": student_id,
            "include": include, "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_enrollment(self, *, enrollment_id: str,
                       include: str | None = None) -> Envelope:
        return self._get(f"/v2/enrollments/{enrollment_id}", {"include": include},
                         template="/v2/enrollments/{id}")

    def update_enrollments(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/enrollments/", {
            "data": [{"type": "enrollments", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def complete_enrollments(self, *, send_notifications: bool,
                             items: list[dict[str, Any]]) -> Envelope:
        return self._send("PATCH", "/v2/enrollments/completion", {
            "send_notifications": send_notifications,
            "data": [{"type": "enrollments", "id": a["id"],
                      "attributes": {k: v for k, v in a.items() if k != "id"}}
                     for a in items]})

    def bulk_enroll(self, *, published_course_id: str, emails: list[str],
                    expires_at: str | None = None) -> Envelope:
        body: dict[str, Any] = {
            "published_course_id": published_course_id,
            "data": [{"type": "enrollments", "attributes": {"email": e}} for e in emails]}
        if expires_at is not None:
            body["expires_at"] = expires_at
        return self._send("POST", "/v2/enrollments/", body)

    def list_certificates(self, *, course_id: str | None = None,
                          student_id: str | None = None, domains: str | None = None,
                          issued_gte: str | None = None, issued_lte: str | None = None,
                          status: str = "all", cursor: str | None = None,
                          page_size: int | None = None) -> Envelope:
        return self._get("/v2/certificates/", {
            "filter[course.id]": course_id, "filter[student.id]": student_id,
            "filter[domains]": domains, "filter[issued_gte]": issued_gte,
            "filter[issued_lte]": issued_lte, "filter[status]": status,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_certificate(self, *, certificate_id: str) -> Envelope:
        return self._get(f"/v2/certificates/{certificate_id}",
                         template="/v2/certificates/{id}")

    def get_course_analytics(self, *, course_id: str,
                             domains: str | None = None) -> Envelope:
        return self._get(f"/v2/analytics/courses/{course_id}",
                         {"filter[domains]": domains},
                         template="/v2/analytics/courses/{course_id}")

    def list_course_ratings(self, *, course_id: str,
                            student_id: str | None = None) -> Envelope:
        return self._get(f"/v2/analytics/courses/{course_id}/ratings/",
                         {"filter[student.id]": student_id},
                         template="/v2/analytics/courses/{course_id}/ratings/")

    def list_students(self, *, email: str | None = None, first_name: str | None = None,
                      last_name: str | None = None, is_inactive: bool | None = None,
                      cursor: str | None = None, page_size: int | None = None) -> Envelope:
        return self._get("/v2/students/", {
            "filter[email]": email, "filter[first_name]": first_name,
            "filter[last_name]": last_name,
            "filter[is_inactive]": None if is_inactive is None else str(is_inactive).lower(),
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_student(self, *, student_id: str) -> Envelope:
        return self._get(f"/v2/students/{student_id}", template="/v2/students/{id}")

    def create_students(self, *, items: list[dict[str, Any]]) -> Envelope:
        return self._send("POST", "/v2/students/", {
            "data": [{"type": "students", "attributes": a} for a in items]})

    def update_students(self, *, items: list[dict[str, Any]]) -> Envelope:
        rows = []
        for a in items:
            entry: dict[str, Any] = {"type": "students",
                                     "attributes": {k: v for k, v in a.items() if k != "id"}}
            if a.get("id"):
                entry["id"] = a["id"]
            rows.append(entry)
        return self._send("PATCH", "/v2/students/", {"data": rows})

    def anonymize_student(self, *, student_id: str) -> Envelope:
        """The ONLY call that sends X-Confirm-Destructive. See `_send`."""
        return self._send("POST", f"/v2/students/{student_id}/anonymize/", {},
                          template="/v2/students/{id}/anonymize/",
                          headers={"X-Confirm-Destructive": "true"})

    def deactivate_student(self, *, student_id: str) -> Envelope:
        return self._send("DELETE", f"/v2/students/{student_id}", {},
                          template="/v2/students/{id}")

    def set_student_password(self, *, student_id: str, password: str) -> Envelope:
        return self._send("POST", f"/v2/students/{student_id}/set-password/",
                          {"data": {"type": "password-sets",
                                    "attributes": {"password": password}}},
                          template="/v2/students/{id}/set-password/")

    def send_password_reset(self, *, student_id: str, domain: str) -> Envelope:
        return self._send("POST",
                          f"/v2/students/{student_id}/send-password-reset/?domain={domain}",
                          {}, template="/v2/students/{id}/send-password-reset/")
