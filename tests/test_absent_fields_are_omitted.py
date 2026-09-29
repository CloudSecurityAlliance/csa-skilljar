"""A field the record does not have is left out, not reported as null.

Nine serialisers copy their optional fields the same way:

    for key in ("rating", "feedback", "created_at"):
        if key in attrs:
            item[key] = attrs[key]

Every fixture in the suite supplies every field, so the FALSE arm of each of those guards
had never run. What was untested is not an error path - it is the ordinary case of a record
that simply does not have a rating yet.

The property is worth stating because the alternative is not a crash, it is a lie of a
particular shape. `{"rating": null}` and a missing `rating` key look similar in a JSON dump
and mean different things to a model reading the result: one says the learner rated nothing,
the other says this record carries no rating field at all. The first is a claim about the
learner. Skilljar's own `total` carries the same distinction - see
`test_v1_bare_array_has_no_total` - and this is the same rule applied to a row instead of a
page.
"""
from __future__ import annotations

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import settings_from_env
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend


def bare_tools(**v2):
    """Tools over backends holding rows with their REQUIRED fields and nothing else."""
    policy = Policy.from_profile("full")
    v1 = FakeV1Backend(assets=[{"id": "a1"}],
                       webhooks=[{"id": "w1", "event_type": "COURSE_COMPLETION"}])
    client = SkilljarClient(PolicyBackend(FakeBackend(**v2), policy),
                            v1=PolicyBackend(v1, policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


def test_an_asset_with_no_name_or_type_reports_neither(fns=None):
    """`asset_type` is `type` renamed on the way out, so its guard is separate from the
    loop above it and needed its own bare row."""
    row = bare_tools()["list_assets"]()["assets"][0]
    assert row["id"] == "a1"
    for absent in ("name", "embed_link_url", "sync_completion", "asset_type"):
        assert absent not in row, f"{absent} was reported for an asset that has none"


def test_a_rating_with_no_score_or_feedback_reports_neither():
    """A rating row that exists because the learner opened the form and left it blank. The
    row is real; the score is not."""
    tools = bare_tools(courses=[{"type": "courses", "id": "c1", "attributes": {"title": "T"}}],
                       course_ratings=[{"type": "course-ratings", "id": "r1",
                                        "attributes": {"course_id": "c1"}}])
    row = tools["list_course_ratings"](course_id="c1")["ratings"][0]
    assert row == {}, (
        "a rating row carries only the three optional fields, so a blank one is an empty "
        f"object - got {row!r}")


def test_a_visibility_override_reports_only_the_keys_it_has():
    tools = bare_tools(groups=[{"type": "groups", "id": "g1", "attributes": {"name": "G"}}])
    tools["add_visibility_overrides"](id="g1", overrides=[{"published_course_id": "pc1"}])
    row = tools["list_visibility_overrides"](id="g1")["overrides"][0]
    assert row["published_course_id"] == "pc1"


class WithoutAssignmentSettings:
    """`FakeBackend.bind_banks` writes `{**defaults, **supplied}`, so an
    assignment it stores always has all three settings and this serialiser's false arm is
    unreachable through it.

    Whether the double should invent those defaults is a separate question - it matches what
    Skilljar returns today. What is being tested here is the SERIALISER's contract, so the
    row is stripped on the way back rather than the double being changed to produce a shape
    it does not currently produce.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name != "list_bank_assignments":
            return attr

        def stripped(**kwargs):
            env = attr(**kwargs)
            bare = []
            for row in env.get("data", []):
                attrs = {k: v for k, v in row.get("attributes", {}).items()
                         if k not in ("order", "randomize_questions",
                                      "limit_question_count")}
                bare.append({**row, "attributes": attrs})
            return {**env, "data": bare}

        return stripped


def test_an_assignment_with_no_ordering_reports_none_of_it():
    """`order`, `randomize_questions` and `limit_question_count` are settings a quiz may
    simply not have set. Reporting them as null invites a caller to 'correct' a value the
    author never chose."""
    policy = Policy.from_profile("full")
    inner = FakeBackend(
        quizzes=[{"type": "quizzes", "id": "qz1", "attributes": {"name": "Q"}}],
        question_banks=[{"type": "question-banks", "id": "qb1",
                         "attributes": {"name": "B"}}])
    inner.bind_banks(quiz_id="qz1", items=[{"question_bank_id": "qb1"}])
    client = SkilljarClient(PolicyBackend(WithoutAssignmentSettings(inner), policy))
    app = create_server(lambda: client, settings=settings_from_env({}))
    fns = {n: t.fn for n, t in app._tool_manager._tools.items()}
    row = fns["list_quiz_question_bank_assignments"](quiz_id="qz1")["assignments"][0]
    assert row["question_bank_id"] == "qb1"
    for absent in ("order", "randomize_questions", "limit_question_count"):
        assert absent not in row


def test_a_signup_value_with_no_label_and_no_relationships_reports_neither():
    """Three guards in a row - the label/value loop, the student relationship, the field
    relationship - and a row can be missing all three at once."""
    tools = bare_tools(signup_field_values=[
        {"type": "signup-field-values", "id": "v1", "attributes": {}}])
    row = tools["list_signup_field_values"]()["values"][0]
    for absent in ("label", "value", "student_id", "signup_field_id"):
        assert absent not in row


def test_a_web_package_with_no_type_reports_none():
    tools = bare_tools(web_packages=[{"type": "web-packages", "id": "wp1",
                                      "attributes": {"content_url": "https://e/p"}}])
    row = tools["list_web_packages"]()["web_packages"][0]
    assert "package_type" not in row


def test_a_published_course_with_no_relationships_reports_no_ids():
    """The relationship ids are read out of `relationships`, and a row that carries none is
    what a sparse fieldset or an un-sideloaded response looks like."""
    tools = bare_tools(published_courses=[
        {"type": "published-courses", "id": "pc1", "attributes": {"title": "T"}}])
    row = tools["list_published_courses"]()["published_courses"][0]
    assert row["id"] == "pc1"
    assert "course_id" not in row
    assert "domain_id" not in row


def test_a_webhook_with_no_target_url_reports_no_host_or_path():
    """`_safe_url` returns an empty mapping for an absent URL, so the host and path keys
    never appear. A webhook with no target is a row mid-configuration, not an error."""
    row = bare_tools()["list_webhooks"]()["rows"][0]
    assert row["id"] == "w1"
    for absent in ("target_host", "target_path", "additional_header_names"):
        assert absent not in row
