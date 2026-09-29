"""No batch tool treats an empty list as a successful no-op.

Thirty-four tools take a required array — `create_courses(courses=[...])`,
`delete_groups(group_ids=[...])`, `bulk_enroll_students(emails=[...])`. Each validates that
array itself, and **the validation is written out by hand twenty times across eleven modules
with no shared helper.** That is the single largest duplication in the server and a strong
candidate for `csa-python-mcp-foundation` to absorb, so what matters until then is whether the
twenty copies still agree.

They do, and this pins it. The invariant:

    an empty batch is REFUSED, and the refusal names the parameter

It matters because the caller who sends one is rarely typing `[]` by hand. They filtered a list
and it came back empty — no courses matched, every student was already enrolled — and a tool
that accepted it would answer *success, nothing changed*, which is indistinguishable from
*success, everything changed* to anything reading the count. The refusal is the only thing that
turns a silent no-op into a question.

**Membership is derived from the registry**, so a batch tool added tomorrow is covered without
anybody remembering this file exists — the same discipline as `test_v2_operation_census.py`.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._config import Settings
from csa_skilljar.mcp.server import create_server
from csa_skilljar.policy import Policy, PolicyBackend


@pytest.fixture(scope="module")
def app():
    client = SkilljarClient(PolicyBackend(FakeBackend(), Policy.from_profile("full")))
    return create_server(lambda: client, settings=Settings(profile="full"))


def placeholder(spec: dict):
    """A value of the right JSON type for a required scalar we are not testing.

    Typed rather than always a string, because a tool with a required boolean would otherwise
    fail schema validation before its own check ran - and the census would record a refusal
    that came from pydantic instead of from the tool.
    """
    kind = spec.get("type")
    if kind == "boolean":
        return False
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "x1"


def batch_tools(app) -> list[tuple[str, str, dict]]:
    """(tool, array parameter, the other required parameters) for every batch tool."""
    found = []
    for tool in asyncio.run(app.list_tools()):
        schema = tool.input_schema or {}
        properties = schema.get("properties", {}) or {}
        required = list(schema.get("required", []) or [])
        array_param = next(
            (n for n in required
             if (properties.get(n) or {}).get("type") == "array"), None)
        if array_param is None:
            continue
        others = {n: placeholder(properties.get(n) or {})
                  for n in required if n != array_param}
        found.append((tool.name, array_param, others))
    return sorted(found)


def test_the_census_finds_the_batch_tools(app):
    """The guard on the guard. If the derivation breaks, every assertion below passes
    vacuously over an empty list and nothing says so."""
    found = batch_tools(app)
    assert len(found) >= 34, f"derived only {len(found)} batch tools; expected 34+"

    names = {n for n, _, _ in found}
    for expected in ("create_courses", "delete_groups", "bulk_enroll_students",
                     "update_students", "bind_quiz_question_banks"):
        assert expected in names, f"{expected} is a batch tool and the census missed it"


def test_no_batch_tool_accepts_an_empty_payload(app):
    """All of them, in one pass.

    Reported as a collected list rather than a first failure, because the interesting answer is
    *which* tools diverged - twenty hand-written copies of one check drift one at a time, and
    seeing one name is much less useful than seeing the set.
    """
    accepted = []
    for name, array_param, others in batch_tools(app):
        try:
            asyncio.run(app.call_tool(name, {array_param: [], **others}))
        except Exception:                        # noqa: BLE001 - refusal is the pass condition
            continue
        accepted.append(name)

    assert accepted == [], (
        "these batch tools accepted an empty payload and reported success:\n  "
        + "\n  ".join(accepted)
        + "\nAn empty batch is almost never typed by hand - it is a filter that matched "
          "nothing - and a success with a zero count reads the same as a success with work "
          "done.")


def test_every_refusal_names_the_parameter_that_was_wrong(app):
    """A caller passing four arguments needs to know which one. `csa-skilljar`'s own
    convention elsewhere is that a refusal names the setting or argument at fault, and these
    twenty copies were written independently - so this checks they all kept it."""
    unnamed = []
    for name, array_param, others in batch_tools(app):
        try:
            asyncio.run(app.call_tool(name, {array_param: [], **others}))
        except Exception as error:               # noqa: BLE001 - the message is the subject
            if array_param not in str(error):
                unnamed.append(f"{name}: {str(error)[:90]}")

    assert unnamed == [], (
        "these refusals did not name the parameter at fault:\n  " + "\n  ".join(unnamed))
