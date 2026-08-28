"""Drive every tool through `call_tool`, not through the library.

Calling the underlying function is shorter and tests almost nothing that matters. The
bugs that reach users live in the delivery layer: a parameter alias that publishes a
correct schema and fails every call, a tool shipped with no description, a TypedDict
that returns null structured content below Python 3.12. Only the protocol path sees them.
"""
import pathlib
import re

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

ROWS = [{"type": "courses", "id": "c1",
         "attributes": {"title": "Zero Trust Foundations", "lesson_count": 4}}]

# Coverage is computed from the registry against this table, so a tool added in Block 2
# shows up as a hole rather than being quietly absent.
EXERCISE = {
    "check_access": {},
    "describe_capabilities": {},
    "report_a_problem": {"what_happened": "nothing, this is a test"},
    "list_courses": {},
    "get_course": {"id": "c1"},
    "list_lessons": {},
    "get_lesson": {"id": "l1"},
    "create_courses": {"courses": [{"title": "New"}]},
    "update_courses": {"courses": [{"id": "c1", "title": "Renamed"}]},
    "create_lessons": {"lessons": [{"course_id": "c1", "type": "HTML",
                                    "title": "New", "content_html": "<p>x</p>"}]},
    "update_lessons": {"lessons": [{"id": "l1", "title": "Renamed"}]},
    "list_quizzes": {},
    "get_quiz": {"id": "q1"},
    "create_quizzes": {"quizzes": [{"name": "New"}]},
    "update_quizzes": {"quizzes": [{"id": "q1", "name": "Renamed"}]},
    "delete_quizzes": {"quiz_ids": ["q1"]},
    "list_questions": {},
    "get_question": {"id": "qu1"},
    "create_questions": {"questions": [{"question_html": "<p>Q?</p>",
                                        "question_type": "FREEFORM",
                                        "quiz_id": "q1", "answers": []}]},
    "update_questions": {"questions": [{"id": "qu1", "question_html": "<p>Changed</p>"}]},
    "delete_questions": {"question_ids": ["qu1"]},
    "list_question_banks": {},
    "get_question_bank": {"id": "b1"},
    "create_question_banks": {"question_banks": [{"name": "New Bank"}]},
    "update_question_banks": {"question_banks": [{"id": "b1", "name": "Renamed"}]},
    "delete_question_banks": {"question_bank_ids": ["b1"]},
    "list_quiz_question_bank_assignments": {"quiz_id": "q1"},
    "bind_quiz_question_banks": {"quiz_id": "q1",
                                 "question_banks": [{"question_bank_id": "b1"}]},
    "update_quiz_question_banks": {"quiz_id": "q1",
                                   "question_banks": [{"question_bank_id": "b1"}]},
    "unbind_quiz_question_banks": {"quiz_id": "q1",
                                   "question_banks": [{"question_bank_id": "b1"}]},
    "list_enrollments": {},
    "get_enrollment": {"id": "e1"},
    "list_certificates": {},
    "get_certificate": {"id": "cert1"},
    "get_course_analytics": {"course_id": "c1"},
    "list_course_ratings": {"course_id": "c1"},
    "update_enrollments": {"enrollments": [{"id": "e1", "due_at": None}]},
    "complete_enrollments": {"send_notifications": False,
                             "enrollments": [{"id": "e1", "success_status": "passed"}]},
    "bulk_enroll_students": {"published_course_id": "pc1",
                             "emails": ["someone@example.org"]},
    "list_students": {},
    "get_student": {"id": "s1"},
    "create_students": {"students": [{"email": "new@example.org"}]},
    "update_students": {"students": [{"id": "s1", "first_name": "New"}]},
    "anonymize_student": {"id": "s1", "confirm": True},
    "deactivate_student": {"id": "s1"},
    "set_student_password": {"id": "s1", "password": "hunter2hunter2", "confirm": True},
    "send_password_reset": {"id": "s1", "domain": "learn.example.org"},
    "list_groups": {},
    "get_group": {"id": "g1"},
    "create_groups": {"groups": [{"name": "New"}]},
    "update_groups": {"groups": [{"id": "g1", "name": "Renamed"}]},
    "delete_groups": {"group_ids": ["g1"]},
    "add_group_memberships": {"id": "g1", "student_ids": ["s1"]},
    "remove_group_memberships": {"id": "g1", "student_ids": ["s1"]},
    "list_signup_field_values": {},
    "get_signup_field_value": {"signup_field_value_id": "v1"},
    "create_signup_field_values": {"student_id": "s1",
                                   "values": [{"id": "f1", "value": "Analyst"}]},
    "update_signup_field_values": {"values": [{"id": "v1", "value": "Analyst"}]},
    "list_published_courses": {},
    "get_published_course": {"id": "pc1"},
    "publish_courses": {"published_courses": [{"course_id": "c1", "domain_id": "d2"}]},
    "update_published_courses": {"published_courses": [{"id": "pc1",
                                                        "open_access": True}]},
    "delete_published_course": {"id": "pc1"},
    "unpublish_published_course": {"id": "pc1"},
    "republish_published_course": {"id": "pc1"},
    "list_visibility_overrides": {"id": "g1"},
    "add_visibility_overrides": {"id": "g1",
                                 "overrides": [{"published_course_id": "pc1"}]},
    "remove_visibility_overrides": {"id": "g1",
                                    "overrides": [{"published_course_id": "pc1"}]},
    "list_domains": {},
    "get_domain": {"id": "d1"},
    "list_web_packages": {},
    "get_web_package": {"id": "wp1"},
    "create_web_packages": {"web_packages": [{"content_url": "https://e.org/p.zip",
                                              "title": "New"}]},
    "update_web_packages": {"web_packages": [{"id": "wp1", "title": "Renamed"}]},
    "delete_web_package": {"id": "wp1"},
    "register_oauth_client": {"client_name": "a client"},
    "list_oauth_clients": {},
    "get_oauth_client": {"id": "cl1"},
    "create_oauth_client": {"name": "New job", "scope_preset": "read_only"},
    "update_oauth_client": {"id": "cl1", "name": "Renamed"},
    "deactivate_oauth_client": {"id": "cl1"},
    "rotate_oauth_client_secret": {"id": "cl1"},
    "list_oauth_scopes": {},
    "revoke_refresh_token": {"token": "rt-abc"},
    "find_learner": {"email": "ada@example.org"},
    "list_learner_progress": {"user_id": "u1"},
    "get_learner_progress": {"user_id": "u1", "published_course_id": "pc1"},
}


LESSON_ROWS = [{"type": "lessons", "id": "l1",
                "attributes": {"title": "Intro", "type": "HTML", "course_id": "c1"}}]
QUIZ_ROWS = [{"type": "quizzes", "id": "q1", "attributes": {"name": "Exam"}}]
BANK_ROWS = [{"type": "question-banks", "id": "b1", "attributes": {"name": "Bank"}}]
ENROLMENT_ROWS = [{"type": "enrollments", "id": "e1", "attributes": {"active": True}}]
CERT_ROWS = [{"type": "certificates", "id": "cert1", "attributes": {"status": "active"}}]
STUDENT_ROWS = [{"type": "students", "id": "s1",
                 "attributes": {"email": "ada@example.org", "is_inactive": False}}]
# `updated_at`, not `modified_at` - groups are one of only two v2 resources spelled
# this way. See tests/test_groups.py.
GROUP_ROWS = [{"type": "groups", "id": "g1", "attributes": {
    "name": "Partners", "rule_email_domains": [], "updated_at": "2026-02-01T00:00:00Z"}}]
PUBLISHED_ROWS = [{"type": "published-courses", "id": "pc1",
                   "attributes": {"slug": "zero-trust", "live": True},
                   "relationships": {
                       "course": {"data": {"type": "courses", "id": "c1"}},
                       "domain": {"data": {"type": "domains", "id": "d1"}}}}]
OAUTH_CLIENT_ROWS = [{"type": "clients", "id": "cl1", "attributes": {
    "name": "Reporting export", "client_id": "cid-cl1", "is_active": True,
    "scope_codenames": ["courses:read"], "ip_allowlist": []}}]
WEB_PACKAGE_ROWS = [{"type": "web-packages", "id": "wp1", "attributes": {
    "title": "Zero Trust SCORM", "display_name": "Zero Trust SCORM",
    "state": "READY", "type": "SCORM", "base_path": "/pkg/wp1/"}}]
DOMAIN_ROWS = [{"type": "domains", "id": "d1",
                "attributes": {"name": "learn.example.org", "access": "PUBLIC"}}]
SIGNUP_VALUE_ROWS = [{"type": "signup-field-values", "id": "v1",
                      "attributes": {"label": "Job title", "value": "Analyst"},
                      "relationships": {
                          "student": {"data": {"type": "students", "id": "s1"}},
                          "signup-field": {"data": {"type": "signup-fields",
                                                    "id": "f1"}}}}]
QUESTION_ROWS = [{"type": "questions", "id": "qu1", "attributes": {
    "question_html": "<p>Q?</p>", "question_type": "FREEFORM", "quiz_id": "q1",
    "answers": []}}]


V1_USERS = [{"user": {"id": "u1", "email": "ada@example.org"},
             "registration_count": 1, "completion_count": 0}]
V1_PROGRESS = {"u1": [{"published_course_id": "pc1", "domain_name": "learn.example.org",
                       "course": {"id": "c1", "title": "Zero Trust", "lesson_count": 10},
                       "course_progress": {"completed_lesson_count": 4},
                       "certificate": None, "all_enrollments": [{"enrollment_id": "e1"}]}]}


def build(profile="full", env=None):
    settings = settings_from_env(env or {})
    policy = Policy.from_profile(profile)
    client = SkilljarClient(PolicyBackend(
        FakeBackend(courses=ROWS, lessons=LESSON_ROWS, quizzes=QUIZ_ROWS,
                    questions=QUESTION_ROWS, question_banks=BANK_ROWS,
                    enrollments=ENROLMENT_ROWS, certificates=CERT_ROWS,
                    students=STUDENT_ROWS, groups=GROUP_ROWS,
                    signup_field_values=SIGNUP_VALUE_ROWS,
                    published_courses=PUBLISHED_ROWS, domains=DOMAIN_ROWS,
                    web_packages=WEB_PACKAGE_ROWS, oauth_clients=OAUTH_CLIENT_ROWS),
        policy),
        # Since Block 11 a client carries BOTH backends, policy-wrapped with the same
        # policy. The protocol suite exercises every registered tool, and three of them
        # are served by v1.
        v1=PolicyBackend(FakeV1Backend(users=V1_USERS, progress=V1_PROGRESS), policy))
    return create_server(lambda: client, settings=settings)


def test_the_readme_tool_count_matches_the_registry():
    """The README's running total is the one number that goes stale every single block.

    This lives here rather than in `scripts/check_docs.py` because that script is
    deliberately stdlib-only - its CI job installs no dependencies - and reaching the
    registry imports httpx. A pattern that matches nothing is a failure, not a pass: a
    claim we can no longer locate is a claim we can no longer verify.
    """
    readme = (pathlib.Path(__file__).resolve().parent.parent / "README.md").read_text()
    claimed = re.findall(r"\*\*(\d+) tools\*\* — \d+ over Skilljar's v2 API", readme)
    assert claimed, "README no longer states its tool count in the form this test checks"
    registered = len(build()._tool_manager._tools)
    for got in claimed:
        assert int(got) == registered, (
            f"README says {got} tools, the server registers {registered}")


def test_the_exercise_table_covers_every_registered_tool():
    registered = set(build()._tool_manager._tools)
    assert registered == set(EXERCISE), (
        f"registry drifted from the exercise table: {sorted(registered ^ set(EXERCISE))}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("name", sorted(EXERCISE))
async def test_every_tool_is_callable_through_the_protocol(name):
    result = await build().call_tool(name, EXERCISE[name])
    assert result is not None
    assert not getattr(result, "is_error", False), f"{name} errored: {result}"


@pytest.mark.anyio
async def test_structured_content_is_populated_not_null():
    """A bare dict return is not serializable for structured output, and a TypedDict
    imported from `typing` rather than `typing_extensions` silently emits no schema
    below 3.12 - tests pass on 3.12+, the 3.10 user sees null and no error anywhere."""
    result = await build().call_tool("list_courses", {})
    assert result.structured_content is not None, (
        "structured output is null - check the TypedDict import in _schemas.py"
    )
    assert result.structured_content["courses"][0]["title"] == "Zero Trust Foundations"


@pytest.mark.anyio
async def test_arguments_survive_the_protocol_boundary():
    """The `Field(alias=...)` trap publishes a correct schema and then fails every call,
    because the SDK dumps the validated model BY ALIAS and calls fn(**kwargs). Passing a
    real argument through `call_tool` is the only thing that catches it."""
    app = build()
    hit = await app.call_tool("list_courses", {"filter_title": "zero"})
    assert len(hit.structured_content["courses"]) == 1
    miss = await app.call_tool("list_courses", {"filter_title": "no-such-course"})
    assert miss.structured_content["courses"] == []


@pytest.mark.anyio
async def test_a_refusal_reaches_the_caller_as_a_readable_error():
    """`call_tool` RAISES ToolError rather than returning a result with is_error set -
    confirmed against mcp 2.1.1, not assumed. The SDK wraps our message as
    "Error executing tool X: <our text>", so the remedy survives the boundary."""
    with pytest.raises(ToolError) as e:
        await build(profile="admin").call_tool("list_courses", {})
    assert "content.read" in str(e.value)
    assert "CSA_SKILLJAR_PROFILE" in str(e.value), (
        "a refusal must name the capability and the setting, not just fail"
    )


@pytest.mark.anyio
async def test_a_missing_credential_reaches_the_caller_as_a_readable_error():
    from csa_skilljar.mcp._config import ClientProvider
    settings = settings_from_env({})
    app = create_server(ClientProvider(settings), settings=settings)
    with pytest.raises(ToolError) as e:
        await app.call_tool("list_courses", {})
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in str(e.value)


@pytest.mark.anyio
async def test_every_tool_publishes_an_object_input_schema():
    """Read from list_tools(), which is the surface a client actually receives - and
    note the published type uses `input_schema`, renamed from `inputSchema` in mcp 2.x."""
    for tool in await build().list_tools():
        schema = tool.input_schema
        assert schema is not None, f"{tool.name} has no input schema"
        assert schema.get("type") == "object", tool.name


def test_typeddicts_are_imported_from_typing_extensions():
    """A static guard for a trap that only fires below Python 3.12.

    On 3.12+ `typing.TypedDict` works with pydantic, so a runtime test of structured
    output cannot catch a wrong import on a modern developer machine - it fails only on
    the 3.10/3.11 CI legs, or silently for a 3.10 user. This reads the source instead, so
    it bites everywhere.
    """
    import pathlib

    import csa_skilljar.mcp._schemas as schemas

    src = pathlib.Path(schemas.__file__).read_text()
    assert "from typing_extensions import" in src, "_schemas.py must import from typing_extensions"
    assert not re.search(r"^from typing import .*\bTypedDict\b", src, re.M), (
        "TypedDict imported from `typing` - below 3.12 pydantic silently emits NO schema, "
        "so tests pass on 3.12+ and the 3.10 user sees null structured content"
    )
