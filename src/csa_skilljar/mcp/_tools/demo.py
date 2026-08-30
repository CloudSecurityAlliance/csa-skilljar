"""The demonstration that is also the end-to-end test.

Follows the CINO pattern in `research/mcp-servers/DEMO-AS-END-TO-END-TEST.md`, which is
marked `[proven]`: built for `csa-google-workspace`, three runs, four real bugs, one of
which had survived a fully green 660-test suite.

Four decisions are inherited rather than invented, and each earns its keep:

**Return the PLAN, not the result.** This tool hands back an ordered list of steps and
the MODEL calls the real tools. Running everything here would block a conversation for
minutes behind one call, and the model would have demonstrated nothing — the tool would
have done the work. It also tests the thing no unit test reaches: whether the tool
descriptions are good enough to use from a standing start.

**Coverage is COMPUTED from the registry**, never from a maintained list. `registered -
exercised` is the gap, so a tool added next block shows up as a hole rather than being
quietly absent, and anything genuinely unsuitable is named WITH ITS REASON. A coverage
report that silently excludes things can be gamed.

**Predict the refusals up front.** The plan says which steps this install's profile will
refuse, so a narrator can say what is being skipped instead of walking someone into it.

**Two facts, not one.** "No errors" and "N of N tools exercised" are reported separately,
because a run that exercised nothing has no errors either (ZD-17).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ... import policy as P
from ...client import SkilljarClient
from ._base import READ, translate_errors

# Learner-facing steps use these and only these. DATA-RESOURCES.md: a transcript
# persists, the organization holds 42,669 real learners, and Skilljar cannot filter by
# domain - so a demo has to START from named addresses rather than narrow a listing.
DEMO_ACCOUNTS = ("kseifried@cloudsecurityalliance.org", "kurt@seifried.org")

# Tools a demonstration should not call, each with the reason. Named rather than omitted:
# an exclusion nobody can see is how a coverage number gets gamed.
# A TUPLE OF PAIRS rather than a dict literal. Bandit reads a dict key
# containing "password", "secret" or "token" mapped to a string as a hardcoded
# credential, and flagged four of these prose reasons. Restructuring removes the finding
# honestly, where four scanner suppressions would only hide it.
_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("report_a_problem", "files a problem report; the demo ends by inviting one instead"),
    ("register_oauth_client", "mints a credential, and binds no organization - a demo "
                              "would leave an orphan client behind"),
    ("create_oauth_client", "mints a real organization credential"),
    ("rotate_oauth_client_secret", "breaks every service using the current secret"),
    ("deactivate_oauth_client", "turns off a credential something may be using"),
    ("revoke_refresh_token", "cannot be confirmed (RFC 7009) and cannot be undone"),
    ("anonymize_student", "irreversibly erases a real person's name and email"),
    ("set_student_password", "account takeover on a real learner"),
    ("send_password_reset", "sends a real person an unexpected password-reset email"),
    ("deactivate_student", "removes a real learner's access"),
    ("delete_groups", "hard delete; cascades to memberships and course visibility"),
    ("unpublish_published_course", "takes a live course away from learners"),
    ("delete_published_course", "same, under a different name"),
    ("republish_published_course", "reassigns a public URL"),
    ("bulk_enroll_students", "enrols real people, who then receive email"),
    ("complete_enrollments", "marks real learners complete"),
    ("get_purchase", "no listing endpoint exists, so a demo has no id to use"),
    ("create_students", "creates a real learner account in the organization"),
    ("update_students", "changes a real person's name or active state"),
    ("create_signup_field_values", "overwrites a real learner's registration answers"),
    ("update_signup_field_values", "same, by a different identifier"),
    ("add_group_memberships", "puts real learners into a group, which can grant course "
                              "access"),
    ("remove_group_memberships", "takes real learners out of one, which can revoke it"),
    ("add_visibility_overrides", "changes which courses a group of real learners can see"),
    ("remove_visibility_overrides", "same, in the other direction"),
    ("publish_courses", "puts content on a customer-facing domain"),
    ("update_published_courses", "changes what anonymous visitors can see"),
    ("update_enrollments", "changes a real learner's progress record"),
    ("create_web_packages", "queues a real outbound fetch and leaves a package behind"),
    ("update_web_packages", "renames a package something may be using"),
    ("delete_web_package", "refused while a live lesson uses it, and soft-deletes "
                           "otherwise"),
    ("update_oauth_client", "changes what a real credential may do"),
)

EXCLUDED: dict[str, str] = dict(_EXCLUSIONS)

_READ_ONLY_NOTE = (
    "READ-ONLY. Nothing in this plan changes anything in Skilljar. Safe to run against "
    "the production organization, which is what these credentials reach.")
_READ_WRITE_NOTE = (
    "READ/WRITE. Steps marked `writes: true` CREATE OR CHANGE REAL DATA in the "
    "organization these credentials reach - there is no sandbox. Every write step is "
    "paired with a cleanup step; run them, and if one is refused you must tidy up by "
    "hand. NO WRITE TOOL IN THIS PROJECT HAS EVER BEEN RUN AGAINST SKILLJAR, so this "
    "mode is unproven by construction: expect to be the first person to find out.")


# Tool -> the v2 scope its backend call needs. Only the v2 tools appear: v1 uses an
# organisation key with no scopes at all, so there is nothing to predict for those.
_SCOPES_BY_TOOL: dict[str, tuple[str, ...]] = {
    "list_courses": ("courses:read",), "get_course": ("courses:read",),
    "list_lessons": ("lessons:read",), "get_lesson": ("lessons:read",),
    "list_quizzes": ("quizzes:read",), "get_quiz": ("quizzes:read",),
    "list_questions": ("quizzes:read",), "get_question": ("quizzes:read",),
    "list_question_banks": ("question-banks:read",),
    "get_question_bank": ("question-banks:read",),
    "list_quiz_question_bank_assignments": ("quizzes:read",),
    "list_published_courses": ("published-courses:read",),
    "get_published_course": ("published-courses:read",),
    "list_domains": ("domains:read",), "get_domain": ("domains:read",),
    "list_students": ("students:read",), "get_student": ("students:read",),
    "list_enrollments": ("enrollments:read",), "get_enrollment": ("enrollments:read",),
    "list_certificates": ("certificates:read",), "get_certificate": ("certificates:read",),
    "get_course_analytics": ("analytics:read",), "list_course_ratings": ("analytics:read",),
    "list_groups": ("student-groups:read",), "get_group": ("student-groups:read",),
    "list_visibility_overrides": ("student-groups:read",),
    "list_signup_field_values": ("signup-fields:read",),
    "get_signup_field_value": ("signup-fields:read",),
    "list_web_packages": ("web-packages:read",), "get_web_package": ("web-packages:read",),
    "list_oauth_clients": ("clients:read",), "get_oauth_client": ("clients:read",),
    "list_oauth_scopes": ("clients:read",),
    "create_courses": ("courses:write",), "update_courses": ("courses:write",),
    "create_lessons": ("lessons:write",), "update_lessons": ("lessons:write",),
    "create_quizzes": ("quizzes:write",), "update_quizzes": ("quizzes:write",),
    "delete_quizzes": ("quizzes:write",), "create_questions": ("quizzes:write",),
    "update_questions": ("quizzes:write",), "delete_questions": ("quizzes:write",),
    "create_question_banks": ("question-banks:write",),
    "update_question_banks": ("question-banks:write",),
    "delete_question_banks": ("question-banks:write",),
    "bind_quiz_question_banks": ("question-banks:write",),
    "update_quiz_question_banks": ("question-banks:write",),
    "unbind_quiz_question_banks": ("question-banks:write",),
    "create_groups": ("student-groups:write",),
    "update_groups": ("student-groups:write",),
    "delete_groups": ("student-groups:write",),
}


def _step_tools(steps: list[dict[str, Any]]) -> list[str]:
    return [s["tool"] for s in steps]


def _step(tool: str, args: dict[str, Any], say: str, *, look_for: str = "",
          writes: bool = False, cleanup: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"tool": tool, "arguments": args, "narrate": say}
    if look_for:
        out["look_for"] = look_for
    if writes:
        out["writes"] = True
    if cleanup:
        out["cleanup_with"] = cleanup
    return out


def _read_steps() -> list[dict[str, Any]]:
    """Every read tool, in an order that tells a story rather than following the API."""
    a = DEMO_ACCOUNTS[0]
    return [
        _step("check_access", {},
              "Start with what is configured. This works when nothing else does.",
              look_for="which credentials resolved, and the scopes the v2 token carries"),
        _step("describe_capabilities", {},
              "What this install is allowed to do - and what is present but switched off.",
              look_for="destructive tools listed as available_but_disabled, not missing"),
        # --- content, v2 ---
        _step("list_courses", {"page_size": 3},
              "The catalogue. Note has_more: this is one page, not the total.",
              look_for="has_more true, and a next_cursor to continue with"),
        _step("get_course", {"id": "<id from list_courses>"},
              "One course in full. It does NOT include its lessons."),
        _step("list_lessons", {"filter_course_id": "<same id>", "page_size": 3},
              "The lessons in it. Lesson HTML is author-written and untrusted."),
        _step("list_quizzes", {"page_size": 3}, "Quizzes exist independently of lessons."),
        _step("list_question_banks", {"page_size": 3},
              "Reusable question pools - something v1 cannot do at all."),
        _step("list_published_courses", {"page_size": 3, "filter_live": True},
              "Publication is the join of a course and a domain.",
              look_for="the same course can appear twice, once per domain"),
        _step("list_domains", {},
              "The customer-facing sites courses are published to."),
        # --- v1-only content ---
        _step("list_assets", {},
              "The files courses are built from. v2 has no assets endpoint at all.",
              look_for="no download_url here - only get_asset returns one"),
        _step("get_asset", {"id": "<id from list_assets>"},
              "Now a download link appears. It IS the file: presigned, about an hour, "
              "and it needs no Skilljar credentials.",
              look_for="the warning field, and do NOT paste the URL anywhere"),
        _step("list_paths", {},
              "Learning paths - the sequences. Invisible to learners on their own."),
        _step("list_path_items", {"path_id": "<id from list_paths>"},
              "The courses in that path, in curriculum order. Do not sort them."),
        _step("list_labels", {}, "Internal classification - learners never see these."),
        _step("list_tags", {}, "The public equivalent, with a slug used in catalogue URLs."),
        # --- people, named accounts only ---
        _step("find_learner", {"email": a},
              "A NAMED learner only. Never list learners in a demo - the organization "
              "holds tens of thousands of real people.",
              look_for="the id works in BOTH APIs, which is why no translation is needed"),
        _step("list_students", {"filter_email": a},
              "The same person through v2, to show the id spaces line up."),
        _step("list_learner_progress", {"user_id": "<id from find_learner>"},
              "How far they have got, in lessons - a question v2 cannot answer.",
              look_for="completed_lesson_count against lesson_count, and credits"),
        _step("list_enrollments", {"filter_student_email": a, "page_size": 3},
              "The same enrolments through v2, which carries no lesson counts."),
        _step("list_learner_path_enrollments", {"user_id": "<id from find_learner>"},
              "Path enrolment is separate from the courses inside the path."),
        _step("list_groups", {"page_size": 3}, "Groups decide who can see which courses."),
        # --- operations ---
        _step("list_certificates", {"filter_student_id": "<id from find_learner>"},
              "Certificates for that learner. An empty result is a real answer."),
        _step("get_course_analytics", {"course_id": "<id from list_courses>"},
              "Aggregate performance for one course - there is no org-wide call."),
        _step("list_vilt_session_events", {"page_size": 3},
              "Scheduled sessions. Read the timezone; 09:00 is 09:00 somewhere."),
        _step("list_ilt_instructors", {},
              "Who teaches them. Rows carry staff names and email addresses."),
        # --- commerce and events ---
        _step("list_offers", {"page_size": 3}, "What is for sale, and at what price."),
        _step("list_promo_codes", {"page_size": 3},
              "Thousands of these. Read total rather than paging through them.",
              look_for="total in the thousands while rows is a handful"),
        _step("list_webhooks", {},
              "Where events are sent. Secrets are withheld from this output.",
              look_for="header NAMES but no values, and a URL with its query stripped"),
        _step("preview_event_payload", {"event_type": "COURSE_COMPLETION"},
              "What a course-completion event looks like. Sample data, not real records."),
        # --- the rest of the read surface, so coverage is real rather than a highlight
        # reel. Ordered after the narrative steps because these fill gaps rather than
        # telling a story.
        _step("list_web_packages", {},
              "SCORM and similar archives. Not paginated - the whole library returns."),
        _step("get_web_package", {"id": "<id from list_web_packages>"},
              "One package. display_name lags title until the package is READY."),
        _step("get_lesson", {"id": "<id from list_lessons>"},
              "One lesson in full, including its content HTML.",
              look_for="the untrusted-content warning; author HTML reaches you here"),
        _step("get_quiz", {"id": "<id from list_quizzes>"}, "One quiz and its settings."),
        _step("list_questions", {"filter_quiz_id": "<id from list_quizzes>", "page_size": 3},
              "Its questions. A question belongs to a quiz OR a bank, never both."),
        _step("get_question", {"id": "<id from list_questions>"},
              "One question, with its answers inline."),
        _step("get_question_bank", {"id": "<id from list_question_banks>"},
              "One reusable pool."),
        _step("list_quiz_question_bank_assignments", {"quiz_id": "<id from list_quizzes>"},
              "How banks are bound to a quiz. Not paginated - the set is bounded."),
        _step("get_published_course", {"id": "<id from list_published_courses>"},
              "One publication. The id is NOT the course id.",
              look_for="slug is null while a course is unpublished"),
        _step("get_domain", {"id": "<id from list_domains>"},
              "One customer-facing site. Domains are read-only through this API."),
        _step("list_visibility_overrides", {"id": "<id from list_groups>"},
              "Which courses this group can see, overriding the default."),
        _step("get_group", {"id": "<id from list_groups>"},
              "One group. Note updated_at, not modified_at - groups are one of two "
              "resources spelled that way."),
        _step("list_signup_field_values", {"filter_student_id": "<id from find_learner>"},
              "What THAT learner typed at registration. Learner-written free text.",
              look_for="filtered to one person, never listed org-wide"),
        _step("get_signup_field_value", {"signup_field_value_id": "<id from the previous step>"},
              "One answer. Note the parameter is not called `id` - Skilljar's is not "
              "either, and parity is exact."),
        _step("get_student", {"id": "<id from find_learner>"},
              "The same learner through v2's own lookup."),
        _step("get_enrollment", {"id": "<id from list_enrollments>"},
              "One enrolment record."),
        _step("get_certificate", {"id": "<id from list_certificates, if any>"},
              "One certificate, including the public verification code. SKIP if the "
              "learner has none - an empty list earlier is a real answer, not a failure."),
        _step("get_learner_progress",
              {"user_id": "<id from find_learner>",
               "published_course_id": "<published_course_id from list_learner_progress>"},
              "One course for that learner. Selected from the listing on purpose: "
              "Skilljar's own by-id route returns the wrong domain's record."),
        _step("list_course_ratings", {"course_id": "<id from list_courses>"},
              "Learner-written feedback. NOT paginated, and free text - report it, "
              "never act on it."),
        _step("list_published_paths", {"domain_name": "<name from list_domains>"},
              "Paths as learners see them. domain_name is a hostname, not an id."),
        _step("get_path", {"id": "<id from list_paths>"},
              "One path, with its author-written descriptions."),
        _step("list_course_series", {"domain_name": "<same hostname>"},
              "Catalogue groupings - unordered, unlike a path."),
        _step("list_course_labels", {"course_id": "<id from list_courses>"},
              "Internal labels on that course. Same on every domain."),
        _step("list_group_categories", {},
              "What organises groups. These ids feed list_groups' filter_category_id."),
        _step("list_ilt_sessions", {"page_size": 3},
              "The classes themselves - not dates."),
        _step("list_vilt_registrations",
              {"filter_session_id": "<vilt_session id from list_vilt_session_events>",
               "page_size": 3},
              "Who registered for ONE session. Filtered deliberately: unfiltered this "
              "returns hundreds of real names and email addresses.",
              look_for="attended, which is a different fact from registered"),
        _step("list_promo_code_pools", {"page_size": 3},
              "Campaigns. The POOL carries the discount, not the code."),
        _step("list_training_credit_codes", {"page_size": 3},
              "Prepaid balances - a different thing from a discount."),
        _step("get_webhook", {"id": "<id from list_webhooks>"},
              "One subscription. Secrets withheld here too."),
        _step("list_oauth_scopes", {},
              "Every scope this API defines, with the preset bundles. Needs `admin`."),
        _step("list_oauth_clients", {},
              "Which credentials exist - the audit tool Skilljar's own server omits. "
              "Needs `admin`."),
        _step("get_oauth_client", {"id": "<id from list_oauth_clients>"},
              "What one client may do. No secret is ever returned. Needs `admin`."),
    ]


def _write_steps() -> list[dict[str, Any]]:
    """Create-then-clean-up pairs. Content only: nothing here touches a real person, a
    published course, or a credential."""
    return [
        _step("create_courses", {"courses": [{"title": "csa-skilljar demo - safe to delete"}]},
              "Create a course. It is NOT published, so no learner can see it.",
              writes=True, cleanup="no delete_courses tool exists - see the warning below",
              look_for="the returned id, which the next steps need"),
        _step("update_courses",
              {"courses": [{"id": "<id from create_courses>",
                            "title": "csa-skilljar demo - renamed"}]},
              "Rename it, to show a batch update round-tripping.", writes=True),
        _step("create_quizzes", {"quizzes": [{"name": "csa-skilljar demo quiz"}]},
              "Create a quiz. Quizzes CAN be deleted, so this one cleans up fully.",
              writes=True, cleanup="delete_quizzes"),
        _step("create_questions",
              {"questions": [{"quiz_id": "<id from create_quizzes>",
                              "question_html": "<p>Is this a demo?</p>",
                              "question_type": "FREEFORM", "answers": []}]},
              "Add a question to it.", writes=True, cleanup="deleted with the quiz"),
        _step("update_questions",
              {"questions": [{"id": "<id from create_questions>",
                              "question_html": "<p>Is this still a demo?</p>"}]},
              "Change the question text. Answers are immutable on update - to change "
              "them you delete the question and make a new one.", writes=True),
        _step("delete_questions", {"question_ids": ["<id from create_questions>"]},
              "Remove the question first, to show deletion works on its own.",
              writes=True),
        _step("delete_quizzes", {"quiz_ids": ["<id from create_quizzes>"]},
              "Remove the quiz. This is the cleanup, and it must actually run.",
              writes=True),
        _step("create_question_banks",
              {"question_banks": [{"name": "csa-skilljar demo bank"}]},
              "Create a question bank - a capability v1 does not have.",
              writes=True, cleanup="delete_question_banks"),
        _step("create_lessons",
              {"lessons": [{"course_id": "<id from create_courses>", "type": "HTML",
                            "title": "csa-skilljar demo lesson",
                            "content_html": "<p>Demo.</p>"}]},
              "Add a lesson to the demo course.", writes=True,
              cleanup="removed with the course, by hand"),
        _step("update_lessons",
              {"lessons": [{"id": "<id from create_lessons>",
                            "title": "csa-skilljar demo lesson - renamed"}]},
              "Rename it. Omitted fields keep their stored values.", writes=True),
        _step("update_question_banks",
              {"question_banks": [{"id": "<id from create_question_banks>",
                                   "name": "csa-skilljar demo bank - renamed"}]},
              "Rename the bank before removing it.", writes=True),
        _step("bind_quiz_question_banks",
              {"quiz_id": "<id from create_quizzes>",
               "question_banks": [{"question_bank_id": "<id from create_question_banks>"}]},
              "Bind the bank to the demo quiz - the capability v1 lacks entirely.",
              writes=True, cleanup="unbind_quiz_question_banks"),
        _step("list_quiz_question_bank_assignments", {"quiz_id": "<id from create_quizzes>"},
              "Confirm the binding took."),
        _step("update_quiz_question_banks",
              {"quiz_id": "<id from create_quizzes>",
               "question_banks": [{"question_bank_id": "<same bank id>", "order": 1}]},
              "Re-binding is a PARTIAL update - omitted fields keep their values.",
              writes=True),
        _step("unbind_quiz_question_banks",
              {"quiz_id": "<id from create_quizzes>",
               "question_banks": [{"question_bank_id": "<same bank id>"}]},
              "Unbind. The bank survives; only the link goes.", writes=True),
        _step("update_quizzes",
              {"quizzes": [{"id": "<id from create_quizzes>",
                            "name": "csa-skilljar demo quiz - renamed"}]},
              "Rename the quiz.", writes=True),
        _step("create_groups",
              {"groups": [{"name": "csa-skilljar demo group - safe to delete"}]},
              "Create an EMPTY group. No members, so deleting it cascades to nothing.",
              writes=True, cleanup="delete_groups"),
        _step("update_groups",
              {"groups": [{"id": "<id from create_groups>",
                           "name": "csa-skilljar demo group - renamed"}]},
              "Rename it. Note: sending category_id as null would CLEAR it.", writes=True),
        _step("delete_groups", {"group_ids": ["<id from create_groups>"]},
              "Delete the group we made. A hard delete - safe only because this one is "
              "empty and we created it seconds ago.", writes=True),
        _step("delete_question_banks", {"bank_ids": ["<id from create_question_banks>"]},
              "And remove it. Deleting a bank unbinds any quiz using it.", writes=True),
    ]


def register_demo_tools(app: MCPServer,
                        get_client: Callable[[], SkilljarClient]) -> None:
    """`app` is captured so coverage can be computed from the LIVE registry."""

    @app.tool(annotations=READ)
    @translate_errors
    def demonstration_plan(mode: str = "read_only") -> dict[str, Any]:
        """Return an ordered plan for demonstrating this server - which YOU then carry out.

        This hands back a list of steps; it does not run them. Call the tools it names, in
        order, substituting ids from earlier steps where a placeholder says so. That is
        the point: the plan tests whether the tool descriptions are good enough to use,
        and a tool that ran everything itself would have demonstrated nothing.

        `mode` is `read_only` (the default) or `read_write`.

          read_only    changes nothing. Safe against the production organization, which
                       is what these credentials reach.
          read_write   also creates and deletes CONTENT - a course, a quiz, a question
                       bank. Never a learner, a publication or a credential. Every write
                       is paired with a cleanup step.

        The plan also reports, before you start:
          * which steps THIS install's profile will refuse, so you can say what is being
            skipped rather than walking into it
          * coverage as `exercised` of `registered`, computed from the live tool registry
            so a newly added tool appears as a gap
          * which tools are deliberately excluded, each with its reason

        When you finish, report two facts SEPARATELY: whether anything errored, and how
        many tools were exercised. A run that did nothing also has no errors.

        Learner steps use named accounts only. Do not substitute a broad listing - the
        organization holds tens of thousands of real people and a transcript outlives the
        demo.
        """
        wanted = mode.strip().lower().replace("-", "_")
        if wanted not in ("read_only", "read_write"):
            raise ValueError(
                f"mode must be 'read_only' or 'read_write'; got {mode!r}")

        steps = _read_steps()
        if wanted == "read_write":
            steps = steps + _write_steps()

        registered = set(app._tool_manager._tools)
        exercised = {s["tool"] for s in steps}
        # Computed, not maintained. A tool added next block lands in `not_exercised` and
        # shows up as a hole rather than being quietly absent.
        remaining = registered - exercised - set(EXCLUDED) - {"demonstration_plan"}
        # In read_only mode a write tool is OUT OF SCOPE, not a gap. Counting it as one
        # made the honest number dishonest in the other direction - it would never reach
        # zero, so nobody would ever look at it.
        write_only = set(_step_tools(_write_steps())) if wanted == "read_only" else set()
        out_of_scope = sorted(remaining & write_only)
        uncovered = sorted(remaining - write_only)

        client = get_client()
        policy = client.policy
        refused = []
        for step in steps:
            gate = P._GATES.get(step["tool"])
            if gate and policy is not None and not policy.allows(gate):
                refused.append({"tool": step["tool"], "needs": gate,
                                "refused_by": "capability profile"})

        # Scopes as well as capabilities. A first live run predicted zero refusals and
        # then hit two, because the credential lacked `clients:read` - the local policy
        # allowed the call and the SCOPE pre-check stopped it. Predicting one and not
        # the other is a prediction that walks you into the other.
        granted = None
        try:
            creds = client.credentials
            granted = creds.granted_scopes() if creds is not None else None
        except Exception:      # noqa: BLE001 - no credential, or it will not grant
            granted = None
        if granted is not None:
            have = set(granted)
            already = {r["tool"] for r in refused}
            for step in steps:
                if step["tool"] in already:
                    continue
                needed = _SCOPES_BY_TOOL.get(step["tool"])
                if needed and not (have & set(needed)):
                    refused.append({"tool": step["tool"], "needs": needed[0],
                                    "refused_by": "OAuth scope on the v2 credential"})

        plan: dict[str, Any] = {
            "mode": wanted,
            "safety": _READ_ONLY_NOTE if wanted == "read_only" else _READ_WRITE_NOTE,
            "steps": steps,
            "coverage": {
                "registered": len(registered),
                "exercised_by_this_plan": len(exercised & registered),
                "excluded_on_purpose": {k: v for k, v in sorted(EXCLUDED.items())
                                        if k in registered},
                "not_exercised": uncovered,
                "out_of_scope_for_this_mode": out_of_scope,
            },
            "will_be_refused": refused,
            "accounts": list(DEMO_ACCOUNTS),
            "how_to_report": (
                "Report TWO separate facts: (1) did anything error, and (2) how many "
                "tools were exercised out of how many registered. A run that exercised "
                "nothing also produced no errors, so the second number is what makes the "
                "first one mean something."),
            "honest_limits": [
                "This exercises the HAPPY PATH, and only the profile this install "
                "happens to have. It cannot enumerate postures, and a gate that refuses "
                "correctly for the wrong reason looks identical from a session.",
                "If several steps are refused, they may all be failing at the SAME gate "
                "- which is one code path tested repeatedly, not several tested once.",
                "A clean run is ambiguous on its own. Pair it with the coverage numbers.",
            ],
        }
        if refused:
            plan["before_you_start"] = (
                f"{len(refused)} step(s) will be REFUSED - see will_be_refused, where "
                f"each says whether it is the capability profile or a missing OAuth "
                f"scope. Say so before starting. A profile is changed with "
                f"CSA_SKILLJAR_PROFILE and a restart; a scope needs the credential "
                f"re-issued in the Skilljar Dashboard.")
        if wanted == "read_write":
            plan["cleanup_warning"] = (
                "THERE IS NO delete_courses TOOL - Skilljar's v2 API does not offer one, "
                "and neither does the official server. The course created by the first "
                "write step CANNOT be removed through this server and must be deleted in "
                "the Skilljar Dashboard by hand. Say that BEFORE creating it, not after.")
            plan["at_the_end"] = (
                "Confirm every cleanup step ran. A demo that narrates cleanup without "
                "doing it leaves real objects behind - which is exactly what happened the "
                "first time this pattern was used elsewhere.")
        else:
            plan["at_the_end"] = (
                "Invite feedback. This is the moment somebody has just formed an opinion "
                "about the server, and it is the cheapest feedback available - "
                "`report_a_problem` files it with the version and profile attached.")
        return plan
