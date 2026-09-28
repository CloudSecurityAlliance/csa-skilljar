"""Every batch tool refuses a malformed batch before any of it reaches Skilljar.

Twenty-seven tools take a list of objects. A JSON schema types the list; it does not say
that item 3 is an object rather than a string, that an update names which record it updates,
or that a batch of nothing is a mistake rather than a no-op. Each of those was decided
per-tool, by hand, twenty-seven times — the arrangement that had drifted on `page_size`
(#102) and on required strings (#104).

Measured 2026-09-28: it has NOT drifted here. All twenty-seven refuse all four shapes, and
every refusal names the parameter and the offending index. So this file pins a property that
currently holds rather than reporting one that does not — which is the point at which a
census is cheapest to add and most likely to be skipped.

**Why the index matters.** A batch of fifty with one bad item is the normal case, and
"courses must be objects" sends the caller back through all fifty by hand. `courses[37]`
does not. That is the same reason the per-item errors carry a JSON Pointer `source`, and it
is the half a "raises ValueError" assertion would not have noticed going missing.
"""
from __future__ import annotations

import inspect

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from .test_pagination import tools


#: Filler for the OTHER required arguments, so the batch under test is the only bad thing in
#: the call. `question_banks` takes exactly one key and `emails` is validated as an address,
#: so those two cannot be a generic placeholder.
def placeholder(p: inspect.Parameter):
    annotation, name = str(p.annotation), p.name
    if name == "emails":
        return ["a@example.org"]
    if name == "question_banks":
        return [{"question_bank_id": "qb0"}]
    if "list[str]" in annotation:
        return ["x"]
    if "list" in annotation:
        return [{"id": "x"}]
    if "bool" in annotation:
        return False
    if "int" in annotation:
        return 1
    return "x"


def batch_tools() -> list[tuple[str, str]]:
    """(tool, parameter) for every required list-of-objects argument, derived."""
    found = []
    for name, fn in sorted(tools()[0].items()):
        for p in inspect.signature(fn).parameters.values():
            if p.default is inspect.Parameter.empty and "list[dict" in str(p.annotation):
                found.append((name, p.name))
    return found


def call(tool: str, param: str, value):
    fn = tools()[0][tool]
    reqs = [p for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty]
    return fn(**{p.name: (value if p.name == param else placeholder(p)) for p in reqs})


def test_the_census_finds_the_batch_tools():
    """A derivation that matched nothing would make every case below a pass — how the filter
    census came to be decorative (#103)."""
    found = batch_tools()
    assert len(found) >= 25, f"derived only {len(found)} batch arguments; expected 25+"
    assert ("create_courses", "courses") in found
    assert ("update_students", "students") in found


@pytest.mark.parametrize("tool, param", batch_tools(), ids=lambda v: v if isinstance(v, str) else v)
def test_an_item_that_is_not_an_object_is_refused_by_index(tool, param):
    """A string where an object belongs is what a caller sends when they pass ids to a tool
    that wants attributes. Refusing it is half the value; saying WHICH one is the other half,
    because the caller cannot see the list from inside the error."""
    with pytest.raises(ToolError, match=rf"{param}\[0\]"):
        call(tool, param, ["notadict"])


@pytest.mark.parametrize("tool, param", batch_tools(), ids=lambda v: v if isinstance(v, str) else v)
def test_an_empty_object_is_refused_by_index(tool, param):
    """`{}` satisfies "is an object" and says nothing. What it is missing differs per tool —
    a required attribute on a create, an id on an update — so this pins the index and the
    refusal rather than the wording, which belongs with the tool."""
    with pytest.raises(ToolError, match=rf"{param}\[0\]"):
        call(tool, param, [{}])


@pytest.mark.parametrize("tool, param", batch_tools(), ids=lambda v: v if isinstance(v, str) else v)
def test_an_empty_batch_is_refused(tool, param):
    """A batch of nothing is a caller that built its list wrong, not a caller asking for
    nothing to happen. Succeeding silently is the worst of the three outcomes: it reports
    success for work that never happened."""
    with pytest.raises(ToolError, match=param):
        call(tool, param, [])


@pytest.mark.parametrize(
    "tool, param", [(t, p) for t, p in batch_tools() if t.startswith("update_")],
    ids=lambda v: v if isinstance(v, str) else v)
def test_an_update_with_no_identifier_is_refused(tool, param):
    """An update that does not say WHICH record it updates is the one malformed batch that
    could plausibly have been sent upstream and applied to something. The identifying key is
    not always `id` — `update_quiz_question_banks` wants `question_bank_id`, `update_students`
    accepts an `id` or an `email` — so what is asserted is that the tool refuses and names
    the item, not which key it asks for."""
    with pytest.raises(ToolError, match=rf"{param}\[0\]"):
        call(tool, param, [{"name": "x", "title": "x", "value": "x"}])
