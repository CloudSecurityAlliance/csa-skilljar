"""Tool descriptions ARE the product (design spec 4.3), so test them like one.

`len(description) > 80` is theatre - it passes for eighty characters of restated tool
name. These assertions encode what a description must tell a model that has never seen
this server: what it returns, what it will NOT return, and what each required argument
is for.

Read from `list_tools()` rather than the internal registry, because that is the surface
a client actually receives.

The conclusive test is a model using the tools cold, which needs a model and so is gated
below. This tier runs in CI on every commit and catches what is mechanically detectable.
"""
import re

import anyio
import pytest

from csa_skilljar.mcp._config import ClientProvider, settings_from_env
from csa_skilljar.mcp.server import create_server


def published():
    s = settings_from_env({})
    app = create_server(ClientProvider(s), settings=s)
    return {t.name: t for t in anyio.run(app.list_tools)}


# Per-tool contract. A new tool with no entry FAILS - the same fail-closed direction as
# policy._GATES, for the same reason.
REQUIREMENTS = {
    "check_access": ["credential", "no call", "relay"],
    "describe_capabilities": ["not enabled", "cannot be changed"],
    "report_a_problem": ["what_happened", "no credential"],
    "list_courses": ["one page", "has_more", "next_cursor", "courses:read", "filter_title"],
    "get_course": ["courses:read", "does not return", "list_lessons"],
    "list_lessons": ["one page", "has_more", "next_cursor", "lessons:read", "exact"],
    "get_lesson": ["lessons:read", "untrusted", "content_html"],
    "create_courses": ["batch", "courses:write", "failed", "title"],
    "update_courses": ["batch", "courses:write", "preserved", "id"],
    "create_lessons": ["batch", "lessons:write", "content_html", "quiz_id"],
    "update_lessons": ["deleted", "confirm_delete_all_content_items",
                       "lessons:write", "preserved", "read-only"],
    "list_quizzes": ["one page", "has_more", "quizzes:read", "exact", "list_questions"],
    "get_quiz": ["quizzes:read", "does not return", "list_questions"],
    "create_quizzes": ["batch", "quizzes:write", "name", "unlimited"],
    "update_quizzes": ["batch", "quizzes:write", "preserved"],
    "delete_quizzes": ["destructive", "untouched", "content.delete", "explicit instruction"],
    "list_questions": ["one page", "has_more", "xor", "get_question"],
    "get_question": ["untrusted", "answers", "list_questions"],
    "create_questions": ["batch", "exactly one", "freeform", "1000"],
    "update_questions": ["immutable", "read-only", "delete_questions", "that row"],
    "delete_questions": ["destructive", "untouched", "content.delete", "question_ids"],
    "list_question_banks": ["one page", "has_more", "question-banks:read", "reusable"],
    "get_question_bank": ["question-banks:read", "not its questions", "list_questions"],
    "create_question_banks": ["batch", "question-banks:write", "empty", "name"],
    "update_question_banks": ["batch", "only writable field", "question-banks:write"],
    "delete_question_banks": ["destructive", "unbound", "untouched", "content.delete"],
    "list_quiz_question_bank_assignments": ["not paginated", "quizzes:read",
                                            "limit_question_count"],
    "bind_quiz_question_banks": ["partial update, not a reset", "keeps its current value",
                                 "quizzes:write", "duplicate_in_batch"],
    "update_quiz_question_banks": ["already", "no-op", "quizzes:write", "not_found"],
    "unbind_quiz_question_banks": ["not deleted", "delete_question_banks", "quizzes:write"],
    "list_enrollments": ["one page", "has_more", "enrollments:read", "per-lesson"],
    "get_enrollment": ["enrollments:read", "score", "success_status"],
    "list_certificates": ["one page", "certificates:read", "defaults to"],
    "get_certificate": ["certificates:read", "issued"],
    "get_course_analytics": ["course_id", "analytics:read", "list_enrollments"],
    "list_course_ratings": ["untrusted", "not paginated", "analytics:read", "never act"],
    "update_enrollments": ["null is invalid", "omit", "enrollments:write", "deactivat"],
    "complete_enrollments": ["required", "email", "explicit instruction",
                             "send_notifications"],
    "bulk_enroll_students": ["real people", "future", "explicit instruction",
                             "published_course_id", "emails"],
    "list_students": ["one page", "has_more", "students:read", "exact"],
    "get_student": ["students:read", "list_enrollments"],
    "create_students": ["batch", "students:write", "does not enrol", "students"],
    "update_students": ["read-only", "confirmation", "two separate calls", "students"],
    "anonymize_student": ["cannot be undone", "confirm=true", "deactivate_student",
                          "people.destructive"],
    "deactivate_student": ["reversible", "people.destructive", "enrolments are"],
    "set_student_password": ["account takeover", "confirm=true", "send_password_reset",
                             "never appears"],
    "send_password_reset": ["required", "list_domains", "people.destructive", "domain"],
    # Groups. Each phrase is a trap from the captured registry that a model would
    # otherwise have to guess about.
    "list_groups": ["one page", "has_more", "next_cursor", "student-groups:read",
                    "case-insensitive", "zero results", "updated_at"],
    "get_group": ["student-groups:read", "does not return", "updated_at"],
    "create_groups": ["batch", "student-groups:write", "unique", "case-sensitive",
                      "1 to 100"],
    "update_groups": ["batch", "student-groups:write", "replaces the whole",
                      "does not merge", "clears the category", "leaves it unchanged"],
    "delete_groups": ["hard delete", "cascades", "visibility", "lose access",
                      "no undo"],
    "add_group_memberships": ["batch", "student-groups:write", "idempotent",
                              "first-wins", "grant course access"],
    "remove_group_memberships": ["batch", "student-groups:write", "idempotent",
                                 "never a member", "revoke course access"],
    # Signup fields. The two id meanings and the untrusted-text warning.
    "list_signup_field_values": ["one page", "has_more", "next_cursor",
                                 "signup-fields:read", "untrusted",
                                 "signup-field-value id", "matches nothing"],
    "get_signup_field_value": ["signup-fields:read", "untrusted",
                               "signup_field_value_id", "not `id`"],
    "create_signup_field_values": ["batch", "signup-fields:write", "upsert",
                                   "overwritten", "signup-field id"],
    "update_signup_field_values": ["batch", "signup-fields:write",
                                   "signup-field-value id", "not the signup-field id"],
}


def test_every_tool_has_a_declared_description_contract():
    missing = set(published()) - set(REQUIREMENTS)
    assert not missing, (
        f"tools with no description contract: {sorted(missing)} - add one, do not delete this test"
    )


@pytest.mark.parametrize("name", sorted(REQUIREMENTS))
def test_description_says_what_a_cold_reader_needs(name):
    desc = (published()[name].description or "").lower()
    for needle in REQUIREMENTS[name]:
        assert needle.lower() in desc, f"{name}: description never mentions {needle!r}"


@pytest.mark.parametrize("name", sorted(REQUIREMENTS))
def test_description_is_not_just_the_tool_name_restated(name):
    desc = (published()[name].description or "").strip()
    first = desc.split("\n")[0].lower()
    words = set(re.findall(r"[a-z_]+", first)) - set(name.split("_"))
    assert len(words) >= 6, f"{name}: first line restates the tool name and says nothing else"


@pytest.mark.parametrize("name", sorted(REQUIREMENTS))
def test_every_required_parameter_is_explained_in_the_description(name):
    tool = published()[name]
    desc = (tool.description or "").lower()
    for param in tool.input_schema.get("required", []):
        assert param.lower() in desc, f"{name}: required parameter {param!r} is never explained"


@pytest.mark.skipif("not config.getoption('--cold-use', default=False)",
                    reason="needs a model; run with --cold-use")
def test_a_model_can_use_these_tools_from_a_standing_start():
    """The conclusive version, and the reason the lint above exists as a cheap proxy.

    Give a model ONLY the tool list - no source, no README, no examples - and a goal. It
    must pick the right tool with the right arguments. This is what
    DEMO-AS-END-TO-END-TEST means by testing whether descriptions are good enough to use
    cold; it is the actual product being measured.

    Deliberately NOT in CI: it costs a model call and is non-deterministic. Run it before
    any release that changes a description.
    """
    pytest.skip("harness lands with Block 2; the contract is documented here")
