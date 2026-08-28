"""Structured-output shapes.

`TypedDict` MUST come from `typing_extensions`, unconditionally: from `typing` below
Python 3.12 pydantic silently emits NO schema - tests pass on 3.12+, the 3.10 user sees
null structured content and no error anywhere.
"""
from __future__ import annotations

from typing import Any

from typing_extensions import NotRequired, TypedDict


class CredentialState(TypedDict):
    configured: bool
    working: NotRequired[bool]
    detail: str


class AccessOut(TypedDict):
    version: str
    profile: str
    v2: CredentialState
    v1: CredentialState
    granted_scopes: list[str]
    # Set only when the token carries no recognised scope claim. Distinct from an empty
    # granted_scopes, which means the client really was issued nothing.
    scopes_unknown: NotRequired[bool]
    expires_in_seconds: NotRequired[float]


class CapabilitiesOut(TypedDict):
    profile: str
    enabled: list[str]
    available_but_disabled: list[str]
    how_to_change: str


class ProblemReportOut(TypedDict):
    report: str
    where_to_file: str


class CourseOut(TypedDict):
    id: str
    title: str
    external_id: NotRequired[str]
    is_published: NotRequired[bool]
    lesson_count: NotRequired[int]


class CourseListOut(TypedDict):
    courses: list[CourseOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class CourseDetailOut(TypedDict):
    id: str
    title: str
    short_description: NotRequired[str]
    long_description_html: NotRequired[str]
    enforce_sequential_navigation: NotRequired[bool]
    external_id: NotRequired[str]
    is_published: NotRequired[bool]
    lesson_count: NotRequired[int]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class LessonOut(TypedDict):
    id: str
    title: str
    type: str
    course_id: NotRequired[str]
    order: NotRequired[int]


class LessonListOut(TypedDict):
    lessons: list[LessonOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class LessonDetailOut(TypedDict):
    id: str
    title: str
    type: str
    course_id: NotRequired[str]
    order: NotRequired[int]
    description_html: NotRequired[str]
    content_html: NotRequired[str]
    quiz_id: NotRequired[str]
    content_items: NotRequired[list[dict[str, Any]]]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class BatchFailureOut(TypedDict):
    code: str
    detail: str
    pointer: str


class BatchResultOut(TypedDict):
    total: int
    succeeded: int
    failed: list[BatchFailureOut]
    ids: list[str]
    note: str


class QuizOut(TypedDict):
    id: str
    name: str
    passing_percentage_correct: NotRequired[int]
    max_attempts: NotRequired[int]


class QuizListOut(TypedDict):
    quizzes: list[QuizOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class QuizDetailOut(TypedDict):
    id: str
    name: str
    description_html: NotRequired[str]
    alignment: NotRequired[str]
    passing_percentage_correct: NotRequired[int]
    max_attempts: NotRequired[int]
    limit_question_count: NotRequired[int]
    time_limit_seconds: NotRequired[int]
    randomize_questions: NotRequired[bool]
    randomize_answers: NotRequired[bool]
    require_correct_response: NotRequired[bool]
    show_question_feedback: NotRequired[bool]
    show_results_on_failure: NotRequired[bool]
    skip_start_screen: NotRequired[bool]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class AnswerOut(TypedDict):
    answer_text: str
    correct: NotRequired[bool]
    order: NotRequired[int]


class QuestionOut(TypedDict):
    id: str
    question_html: str
    question_type: str
    quiz_id: NotRequired[str]
    question_bank_id: NotRequired[str]
    order: NotRequired[int]


class QuestionListOut(TypedDict):
    questions: list[QuestionOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class QuestionDetailOut(TypedDict):
    id: str
    question_html: str
    question_type: str
    answers: list[AnswerOut]
    quiz_id: NotRequired[str]
    question_bank_id: NotRequired[str]
    order: NotRequired[int]
    correct_answer_feedback_html: NotRequired[str]
    incorrect_answer_feedback_html: NotRequired[str]
    answer_feedback_html: NotRequired[str]
    case_sensitive: NotRequired[bool]
    is_graded: NotRequired[bool]
    is_optional: NotRequired[bool]
    requires_manual_grading: NotRequired[bool]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class QuestionBankOut(TypedDict):
    id: str
    name: str
    question_count: NotRequired[int]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class QuestionBankListOut(TypedDict):
    question_banks: list[QuestionBankOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class AssignmentOut(TypedDict):
    question_bank_id: str
    order: NotRequired[int]
    randomize_questions: NotRequired[bool]
    limit_question_count: NotRequired[int]


class AssignmentListOut(TypedDict):
    quiz_id: str
    assignments: list[AssignmentOut]
    note: str


class EnrollmentOut(TypedDict):
    id: str
    active: NotRequired[bool]
    progress_status: NotRequired[str]
    success_status: NotRequired[str]
    score: NotRequired[int]
    max_score: NotRequired[int]
    enrolled_at: NotRequired[str]
    completed_at: NotRequired[str]
    due_at: NotRequired[str]
    expires_at: NotRequired[str]
    has_certificate: NotRequired[bool]
    domain_name: NotRequired[str]
    channel: NotRequired[str]
    source: NotRequired[str]


class EnrollmentListOut(TypedDict):
    enrollments: list[EnrollmentOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class CertificateOut(TypedDict):
    id: str
    status: NotRequired[str]
    issued_at: NotRequired[str]
    expires_at: NotRequired[str]
    code: NotRequired[str]
    score_as_percent: NotRequired[float | None]


class CertificateListOut(TypedDict):
    certificates: list[CertificateOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class CourseAnalyticsOut(TypedDict):
    course_id: str
    attributes: dict[str, Any]
    note: str


class RatingOut(TypedDict):
    rating: NotRequired[int]
    feedback: NotRequired[str]
    created_at: NotRequired[str]


class RatingListOut(TypedDict):
    course_id: str
    ratings: list[RatingOut]
    note: str


class StudentOut(TypedDict):
    id: str
    email: NotRequired[str]
    first_name: NotRequired[str]
    last_name: NotRequired[str]
    is_inactive: NotRequired[bool]
    external_id: NotRequired[str]
    date_joined: NotRequired[str]


class StudentListOut(TypedDict):
    students: list[StudentOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class AnonymizeOut(TypedDict):
    id: str
    anonymized: bool
    note: str


class DeactivateOut(TypedDict):
    id: str
    deactivated: bool
    note: str


class PasswordOut(TypedDict):
    id: str
    note: str


class PasswordResetOut(TypedDict):
    id: str
    sent: bool
    domain: str
    note: str


class GroupOut(TypedDict):
    id: str
    name: str
    rule_email_domains: NotRequired[list[str]]
    send_course_enrollment_email: NotRequired[bool | None]
    category_id: NotRequired[str | None]
    created_at: NotRequired[str]
    # `updated_at`, NOT `modified_at`. Groups and visibility overrides are the only two
    # v2 resources that spell it this way; the other twelve use modified_at. Renaming
    # this to match the majority makes the field vanish from output with no error.
    updated_at: NotRequired[str]


class GroupListOut(TypedDict):
    groups: list[GroupOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class MembershipResultOut(TypedDict):
    group_id: str
    total: int
    succeeded: int
    failed: list[dict[str, Any]]
    student_ids: list[str]
    note: str


class SignupFieldValueOut(TypedDict):
    id: str
    label: NotRequired[str]
    value: NotRequired[str]
    student_id: NotRequired[str]
    signup_field_id: NotRequired[str]


class SignupFieldValueListOut(TypedDict):
    values: list[SignupFieldValueOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class PublishedCourseOut(TypedDict):
    id: str
    course_id: NotRequired[str]
    domain_id: NotRequired[str]
    slug: NotRequired[str | None]
    live: NotRequired[bool]
    is_hidden: NotRequired[bool]
    visible_on_catalog: NotRequired[bool]
    open_access: NotRequired[bool]
    strict_enforce_group_visibility: NotRequired[bool]
    visibility_override_type: NotRequired[str]
    access_period_starts_at: NotRequired[str | None]
    access_period_ends_at: NotRequired[str | None]
    restrict_access_start_end_dates: NotRequired[bool]
    allow_self_service_reenroll: NotRequired[bool]
    unique_progress_per_enrollment: NotRequired[bool]
    require_all_prerequisites: NotRequired[bool]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class PublishedCourseListOut(TypedDict):
    published_courses: list[PublishedCourseOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class DomainOut(TypedDict):
    id: str
    name: str
    access: NotRequired[str]
    access_message_html: NotRequired[str]
    marketing_message: NotRequired[str]
    require_https: NotRequired[bool]
    external_id: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class DomainListOut(TypedDict):
    domains: list[DomainOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class VisibilityOverrideOut(TypedDict):
    id: str
    published_course_id: NotRequired[str]
    is_visible: NotRequired[bool]
    created_at: NotRequired[str]
    # `updated_at`, NOT `modified_at`. Visibility overrides and groups are the only two
    # v2 resources spelled this way. See tests/test_groups.py.
    updated_at: NotRequired[str]


class VisibilityOverrideListOut(TypedDict):
    group_id: str
    overrides: list[VisibilityOverrideOut]
    has_more: bool
    next_cursor: NotRequired[str]
    note: str


class WebPackageOut(TypedDict):
    id: str
    title: NotRequired[str]
    # NOT the same as `title` until `state` is READY. See _tools/web_packages.py.
    display_name: NotRequired[str]
    state: NotRequired[str]
    package_type: NotRequired[str]
    base_path: NotRequired[str]
    created_at: NotRequired[str]
    modified_at: NotRequired[str]


class WebPackageListOut(TypedDict):
    web_packages: list[WebPackageOut]
    note: str


class RegisteredClientOut(TypedDict):
    client_id: str
    client_secret: NotRequired[str | None]
    client_name: NotRequired[str]
    redirect_uris: NotRequired[list[str]]
    grant_types: NotRequired[list[str]]
    token_endpoint_auth_method: NotRequired[str]
    scope: NotRequired[str]
    warning: str


class OAuthClientOut(TypedDict):
    id: str
    name: NotRequired[str]
    description: NotRequired[str | None]
    client_id: NotRequired[str]
    is_active: NotRequired[bool]
    scope_codenames: NotRequired[list[str]]
    ip_allowlist: NotRequired[list[str]]
    created_at: NotRequired[str]
    # Present ONLY on create and rotate. Never on a read - upstream does not store it in
    # a retrievable form, and neither does this.
    client_secret: NotRequired[str]
    warning: NotRequired[str]


class OAuthClientListOut(TypedDict):
    clients: list[OAuthClientOut]
    note: str


class ScopeOut(TypedDict):
    codename: str
    description: NotRequired[str]
    category: NotRequired[str]


class ScopeCatalogueOut(TypedDict):
    scopes: list[ScopeOut]
    presets: dict[str, list[str]]
    note: str


class RevocationOut(TypedDict):
    requested: bool
    note: str
