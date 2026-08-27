"""Live Skilljar. Skipped unless CSA_SKILLJAR_INTEGRATION=1.

This is the fake/real seam guard. A fake is always more permissive than reality - a
soft-deleted-comment-shaped bug survived 660 green tests in csa-google-workspace for
exactly that reason. Behaviour only `V2Backend` has (opaque cursors, upstream error
translation, the 422 boundary) is not provable against `FakeBackend`.

Everything here is READ-ONLY, and that is ENFORCED rather than promised. `live_client`
is wrapped so any mutating call raises before it reaches the network. Until there is a
Skilljar sandbox or a disposable fixture organization (`WAITING-FOR-003`), the only
organization available is CSA's production one, with 42,669 real learners in it.
"""
from __future__ import annotations

import os
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    """Skip ONLY the tests in this directory.

    `pytest_collection_modifyitems` is a session hook: even declared in a subdirectory
    conftest it receives EVERY collected item. Marking them all skipped this way turned
    a 216-test suite into "227 skipped" while every gate still reported OK - which is
    ZD-17 exactly, an absence-shaped failure that no error-shaped check can see.
    """
    if os.environ.get("CSA_SKILLJAR_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="set CSA_SKILLJAR_INTEGRATION=1 to run against real Skilljar")
    for item in items:
        if HERE in pathlib.Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


# Hand-written, and FAIL-CLOSED: a method absent from this set is refused, not allowed.
# Deriving it from `policy._GATES` by looking for capabilities ending in `.read` would
# be shorter and would silently permit anything a future gate mislabels - the control
# would agree with the bug. This list is the second opinion.
READ_ONLY_METHODS = frozenset({
    "get_certificate", "get_course", "get_course_analytics", "get_domain",
    "get_enrollment", "get_group", "get_lesson", "get_published_course", "get_question",
    "get_question_bank", "get_quiz", "get_signup_field_value", "get_student",
    "get_web_package", "list_bank_assignments", "list_certificates",
    "list_course_ratings", "list_courses", "list_domains", "list_enrollments",
    "list_groups", "list_lessons", "list_published_courses", "list_question_banks",
    "list_questions", "list_quizzes", "list_signup_field_values", "list_students",
    "list_visibility_overrides", "list_web_packages",
})


class WouldHaveWritten(AssertionError):
    """A test tried to mutate the live organization. Deliberately an AssertionError:
    this is a test-suite bug, not a Skilljar failure, and it must never be caught by an
    `except SkilljarError` in the code under test."""


class ReadOnlyClient:
    """Wraps the live client and refuses anything not on the read-only list.

    The docstring above used to say "nothing here writes" and nothing enforced it. The
    suite was read-only by habit, and a habit is not a control: one `create_courses` in
    a new test would have written to CSA's production organization, and the first person
    to notice would have been a learner.
    """

    def __init__(self, inner):
        self._inner = inner

    @property
    def credentials(self):
        return self._inner.credentials

    def __getattr__(self, name):
        if name.startswith("_"):
            return getattr(self._inner, name)
        if name not in READ_ONLY_METHODS:
            raise WouldHaveWritten(
                f"`{name}` is not on the read-only list, so the integration suite will "
                f"not call it. The only organization these credentials reach is CSA's "
                f"production one, with real learners in it. See WAITING-FOR-003 for the "
                f"fixture-organization question. If `{name}` really is a pure read, add "
                f"it to READ_ONLY_METHODS in this file and say why in the commit.")
        return getattr(self._inner, name)

    def __repr__(self):
        return f"ReadOnlyClient({self._inner!r})"


@pytest.fixture(scope="session")
def live_client():
    from csa_skilljar.mcp._config import ClientProvider, settings_from_env
    settings = settings_from_env(os.environ)
    if not (settings.v2_client_id and settings.v2_client_secret):
        pytest.skip("CSA_SKILLJAR_V2_CLIENT_ID / _SECRET not set")
    return ReadOnlyClient(ClientProvider(settings)())


@pytest.fixture(scope="session")
def unguarded_live_client():
    """The raw client, for the guard's own tests only. Nothing else may use this."""
    from csa_skilljar.mcp._config import ClientProvider, settings_from_env
    settings = settings_from_env(os.environ)
    if not (settings.v2_client_id and settings.v2_client_secret):
        pytest.skip("CSA_SKILLJAR_V2_CLIENT_ID / _SECRET not set")
    return ClientProvider(settings)()
