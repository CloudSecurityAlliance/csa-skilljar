"""The per-field rules the batch censuses deliberately do not cover.

`test_batch_item_shapes.py` asserts what is true of every batch tool: an item must be an
object, a batch must not be empty, an update must identify itself, an unknown attribute is
refused. Those are derivable, so they are derived.

What is left is the opposite kind of rule - a length, an enumeration, a numeric range, a
combination that contradicts itself. Each is true of ONE field on ONE tool and none of them
can be derived from a signature, so each is written out. They are the cases a census cannot
reach, which is exactly why they are the ones that go untested: the census makes the file
look thorough and these sit underneath it.

Every one of them was uncovered before this file existed.
"""
from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend

from .test_pagination import backend as v2_backend
from .test_pagination import tools, v1_backend


@pytest.fixture(scope="module")
def fns():
    return tools()[0]


@pytest.fixture(scope="module")
def contactable():
    """`bulk_enroll_students` is refused outright unless the policy allows contacting real
    people, and that refusal fires before any argument is looked at - so the expiry rule
    below is unreachable through the default fixture."""
    policy = Policy.from_profile("full", may_contact_people=True)
    client = SkilljarClient(PolicyBackend(v2_backend(), policy),
                            v1=PolicyBackend(v1_backend(), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


# --- combinations that contradict themselves -----------------------------------------

def test_a_scope_list_and_a_scope_preset_cannot_both_be_sent(fns):
    """Silently preferring one would be the tempting fix and the wrong one: the caller
    believes they asked for both, and the credential that comes back is narrower or wider
    than the one they think they have."""
    with pytest.raises(ToolError, match="scope_codenames OR scope_preset"):
        fns["update_oauth_client"](id="oc1", scope_codenames=["courses:read"],
                                   scope_preset="read_only")


# --- values of the wrong shape --------------------------------------------------------

def test_an_expiry_that_is_not_a_timestamp_says_so(contactable):
    """`expires_at` goes through `datetime.fromisoformat`, and a bare ValueError from the
    stdlib reads "Invalid isoformat string" with no mention of which argument. Re-raising
    with the field name is what makes it correctable."""
    with pytest.raises(ToolError, match="expires_at"):
        contactable["bulk_enroll_students"](published_course_id="pc0",
                                            emails=["a@example.org"],
                                            expires_at="next tuesday")


def test_rule_email_domains_must_be_a_list(fns):
    """A single domain as a bare string is the natural mistake, and it is one Python would
    otherwise accept and iterate CHARACTER BY CHARACTER - creating a rule for the domain
    "e", the domain "x", and so on."""
    with pytest.raises(ToolError, match="rule_email_domains"):
        fns["create_groups"](groups=[{"name": "G", "rule_email_domains": "example.org"}])


def test_a_member_id_must_be_a_non_empty_string(fns):
    with pytest.raises(ToolError, match="student id"):
        fns["add_group_memberships"](id="g0", student_ids=[""])


def test_lesson_content_must_be_a_list_of_items(fns):
    with pytest.raises(ToolError, match="list of content items"):
        fns["create_lessons"](lessons=[{"title": "L", "course_id": "co0",
                                        "type": "MODULAR",
                                        "content_items": {"not": "a list"}}])


def test_question_answers_must_be_a_list(fns):
    with pytest.raises(ToolError, match="answers must be a list"):
        fns["create_questions"](questions=[{"quiz_id": "qz0", "question_html": "<p>?</p>",
                                            "question_type": "MULTIPLE_CHOICE",
                                            "answers": {"not": "a list"}}])


# --- lengths and ranges ---------------------------------------------------------------

def test_a_quiz_name_is_capped_at_500_characters(fns):
    with pytest.raises(ToolError, match="at most 500 characters"):
        fns["create_quizzes"](quizzes=[{"name": "q" * 501}])


def test_a_question_bank_name_is_capped_and_cannot_be_empty(fns):
    """Both arms of one guard - `not attrs["name"] or len(...) > 500`. An empty name passes
    "is a string" and produces a bank nobody can find again."""
    with pytest.raises(ToolError, match="name"):
        fns["create_question_banks"](question_banks=[{"name": "b" * 501}])
    with pytest.raises(ToolError, match="name"):
        fns["create_question_banks"](question_banks=[{"name": ""}])


def test_a_question_bank_count_must_fit_in_a_32_bit_integer(fns):
    """2147483647 is Postgres' `integer` ceiling, and a value above it is rejected by the
    database rather than by the API - which surfaces as a 500 rather than as a message
    naming the field.

    On the ASSIGNMENT, not the bank: `name` is the only writable field on a question bank,
    and `order` and `limit_question_count` belong to the row that binds a bank to a quiz."""
    with pytest.raises(ToolError, match="order is out of range"):
        fns["bind_quiz_question_banks"](
            quiz_id="qz0", question_banks=[{"question_bank_id": "qb0",
                                            "order": 2147483648}])


def test_an_oauth_client_name_is_capped_at_255_characters(fns):
    with pytest.raises(ToolError, match="at most 255 characters"):
        fns["register_oauth_client"](client_name="c" * 256)


def test_an_answer_carries_only_its_text_and_whether_it_is_correct(fns):
    """`{"answer_text": ..., "correct": ..., "is_correct": ...}` is the shape a caller
    writes when guessing, and the guessed key would be dropped silently - producing a
    question whose right answer is whichever one Skilljar defaulted to."""
    with pytest.raises(ToolError, match="is_correct"):
        fns["create_questions"](questions=[{
            "quiz_id": "qz0", "question_html": "<p>?</p>",
            "question_type": "MULTIPLE_CHOICE",
            "answers": [{"answer_text": "a", "correct": True, "is_correct": True}]}])


# --- enumerations and combinations ----------------------------------------------------

def test_a_quiz_alignment_must_be_one_of_the_three(fns):
    with pytest.raises(ToolError, match="alignment"):
        fns["create_quizzes"](quizzes=[{"name": "Q", "alignment": "justified"}])


def test_a_freeform_question_cannot_carry_answer_feedback(fns):
    """FREEFORM has no answer to be right about, so `correct_answer_feedback_html` is
    feedback that can never be shown. Accepting it stores a field the author will believe
    their learners are reading."""
    with pytest.raises(ToolError, match="answer feedback does not apply"):
        fns["create_questions"](questions=[{
            "quiz_id": "qz0", "question_html": "<p>?</p>", "question_type": "FREEFORM",
            "correct_answer_feedback_html": "<p>well done</p>"}])
