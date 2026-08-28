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
    # Publishing. The public-facing block, so the phrases are about blast radius.
    "list_published_courses": ["one page", "has_more", "next_cursor",
                               "published-courses:read", "both live and unpublished",
                               "filter_live"],
    "get_published_course": ["published-courses:read", "not the course id", "slug",
                             "live"],
    "publish_courses": ["batch", "published-courses:write", "course_id", "domain_id",
                        "create-only", "anonymous", "default true",
                        "already_published"],
    "update_published_courses": ["batch", "published-courses:write", "cannot change",
                                 "silently ignores", "clears", "anonymous"],
    "unpublish_published_course": ["published-courses:write", "frees the slug",
                                   "reversible", "republish_published_course"],
    "republish_published_course": ["published-courses:write", "reassigns",
                                   "public url will be different"],
    "delete_published_course": ["published-courses:write", "soft unpublish",
                                "nothing is destroyed", "unpublish_published_course"],
    "list_domains": ["one page", "has_more", "next_cursor", "domains:read", "exact",
                     "read-only"],
    "get_domain": ["domains:read", "read-only", "public", "not instructions"],
    # Visibility overrides - gated by student-groups:*, hence with the group family.
    "list_visibility_overrides": ["one page", "has_more", "next_cursor",
                                  "student-groups:read", "group id", "updated_at",
                                  "empty list"],
    "add_visibility_overrides": ["batch", "student-groups:write", "allowlist",
                                 "blocklist", "idempotent", "published_course_id"],
    "remove_visibility_overrides": ["batch", "student-groups:write", "revoke access",
                                    "grant access", "echo"],
    # Web packages - the asynchronous family, where "succeeded" means "queued".
    "list_web_packages": ["web-packages:read", "not paginated", "ready"],
    "get_web_package": ["web-packages:read", "polling tool", "processing", "error",
                        "display_name"],
    "create_web_packages": ["asynchronous", "web-packages:write", "content_url",
                            "does not mean the package works", "no deduplication",
                            "rate limited"],
    "update_web_packages": ["batch", "web-packages:write", "only writable field",
                            "silently ignores", "look like it did nothing"],
    "delete_web_package": ["web-packages:write", "refused", "live", "soft"],
    "register_oauth_client": ["mints a credential", "unauthenticated", "client_name",
                              "cannot be retrieved again", "no organization is bound",
                              "admin"],
    # Block 10 — credential administration. Every phrase is something a model would
    # otherwise get wrong in a way the response cannot correct.
    "list_oauth_clients": ["clients:read", "admin", "no secrets", "not paginated"],
    "get_oauth_client": ["clients:read", "admin", "is_active", "scope_codenames",
                         "no way to read one back"],
    "list_oauth_scopes": ["clients:read", "admin", "presets", "before creating"],
    "create_oauth_client": ["clients:write", "admin", "not `register_oauth_client`",
                            "bound to your organization", "reads nothing", "not both",
                            "shown once"],
    "update_oauth_client": ["clients:write", "admin", "replaces", "next token",
                            "rotate the secret"],
    "deactivate_oauth_client": ["clients:write", "admin", "deactivation, not a deletion",
                                "do not report it as deleted"],
    "rotate_oauth_client_secret": ["clients:write", "admin", "immediately",
                                   "shown once", "revoke_refresh_token"],
    "revoke_refresh_token": ["admin", "not evidence", "rfc 7009", "typo",
                             "sends no credentials"],
    # Block 11 — served by v1. Each phrase is something the v2 half cannot answer, or a
    # live-API behaviour that is not in Skilljar's published v1 document.
    "list_learner_progress": ["csa_skilljar_v1_api_key", "separate credential",
                              "counts only, not which lessons", "404",
                              "completed_lesson_count", "list_students",
                              "not paginated"],
    "get_learner_progress": ["csa_skilljar_v1_api_key", "on a particular domain",
                             "counts only, not which lessons", "not-found"],
    "find_learner": ["csa_skilljar_v1_api_key", "both apis", "exact",
                     "empty list", "total"],
    # Block 12 — the presigned-URL properties, which land outside this system.
    "list_assets": ["csa_skilljar_v1_api_key", "no download links here",
                    "content_asset_id", "pdf", "one response"],
    "get_asset": ["csa_skilljar_v1_api_key", "is the file, not a reference to it",
                  "no skilljar credentials", "different every time",
                  "do not store or cache it"],
    # Block 13 — read-only commerce. The phrases are about scale and about which
    # record actually holds the money.
    "list_promo_codes": ["read-only", "thousands", "total", "filter_code",
                         "not the same as zero remaining", "csa_skilljar_v1_api_key"],
    "list_promo_code_pools": ["carries the discount", "percent_off", "expire_content",
                              "csa_skilljar_v1_api_key"],
    "list_offers": ["exactly one of which is set", "price_credits",
                    "discounts live in promo-code pools", "csa_skilljar_v1_api_key"],
    "list_training_credit_codes": ["carries a balance", "credits_used",
                                   "tracking_identifier", "csa_skilljar_v1_api_key"],
    "get_purchase": ["no way to list or search purchases", "webhook",
                     "say that rather than searching", "csa_skilljar_v1_api_key"],
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
