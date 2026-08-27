"""Structured-output shapes.

`TypedDict` MUST come from `typing_extensions`, unconditionally: from `typing` below
Python 3.12 pydantic silently emits NO schema - tests pass on 3.12+, the 3.10 user sees
null structured content and no error anywhere.
"""
from __future__ import annotations

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
