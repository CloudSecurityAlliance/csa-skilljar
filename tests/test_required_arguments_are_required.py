"""Every required argument refuses an empty value, and none of them reaches Skilljar.

Fifty-eight parameters across the tool surface have no default, which is the schema saying
the caller must supply one. A JSON schema can require that the KEY is present; it cannot
require that the value means anything, so `""` satisfies the schema and arrives as a real
call. What happens next was decided fifty-eight times by hand.

Two of them decided nothing: `list_course_ratings(course_id="")` returned an empty rating
list, and `report_a_problem(what_happened="")` assembled a report with a blank description
and told the caller where to file it. Both look like answers.

The property is uniform even though the wording is not. Unlike `page_size` - whose message
was byte-identical on all twenty-nine tools and so moved into `translate_errors` - these
messages carry routing a caller needs (`the webhook id, from list_webhooks`), and a generic
refusal would enforce consistency by deleting the useful half. So the BEHAVIOUR is pinned
here, across all of them, and the WORDING stays with the tool.

Membership is derived from the signatures, so a tool that grows a required argument next
block is covered without anyone remembering.
"""
from __future__ import annotations

import inspect

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from .test_pagination import tools


#: Values for the OTHER required arguments of a call, so the one under test is the only
#: empty thing in it. They do not need to resolve to anything: every call here must be
#: refused before it reaches the backend, and a call that gets far enough to 404 has still
#: told us the argument was read.
def placeholder(p: inspect.Parameter):
    annotation, name = str(p.annotation), p.name
    if name == "emails":
        return ["a@example.org"]                    # a real address, or the email guard fires
    if name == "question_banks":
        return [{"question_bank_id": "qb0"}]        # the only key this shape accepts
    if "list[str]" in annotation:
        return ["x"]
    if "list" in annotation:
        return [{"id": "x", "name": "x", "value": "x",
                 "question_html": "<p>?</p>", "content_url": "https://e/x"}]
    if "bool" in annotation:
        return False
    if "int" in annotation:
        return 1
    return "x"


def required_strings() -> list[tuple[str, str]]:
    """(tool, parameter) for every required string argument on the surface."""
    found = []
    for name, fn in sorted(tools()[0].items()):
        for p in inspect.signature(fn).parameters.values():
            if p.default is inspect.Parameter.empty and str(p.annotation) in ("str", "<class 'str'>"):
                found.append((name, p.name))
    return found


def test_the_census_is_not_empty():
    """A derivation that matched nothing would turn every case below into a pass, which is
    exactly how the filter census came to be decorative (#103)."""
    found = required_strings()
    assert len(found) >= 55, f"derived only {len(found)} required strings; expected 55+"
    assert ("get_course", "id") in found
    assert ("report_a_problem", "what_happened") in found


@pytest.mark.parametrize("tool, param", required_strings(),
                         ids=lambda v: v if isinstance(v, str) else v)
def test_an_empty_required_argument_is_refused(tool, param):
    """The whole property. A schema can require the key; only the tool can require that the
    value means something.

    `ToolError` specifically, not any exception: the SDK discards the message of anything
    else and the caller sees "Error executing tool X" with no way to correct itself. All
    fifty-eight refuse this way today, so pinning the TYPE costs nothing and catches a guard
    that starts raising something the user will never get to read."""
    fn = tools()[0][tool]
    reqs = [p for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty]
    kwargs = {p.name: ("" if p.name == param else placeholder(p)) for p in reqs}
    with pytest.raises(ToolError):
        fn(**kwargs)


def guarded() -> list[tuple[str, str]]:
    """The subset whose tool refuses an empty value ITSELF, rather than letting the backend
    404 it.

    The distinction is the whole point and it is invisible from outside a `pytest.raises`:
    a guard refusing and a backend saying "no such id" are both an exception. Only one of
    them stops the request leaving the process. So membership here is measured, not listed -
    a tool that refuses `""` with its own message is one that has an opinion about the
    argument, and the case below says that opinion must cover `"   "` too.
    """
    found = []
    for tool, param in required_strings():
        fn = tools()[0][tool]
        reqs = [p for p in inspect.signature(fn).parameters.values()
                if p.default is inspect.Parameter.empty]
        kwargs = {p.name: ("" if p.name == param else placeholder(p)) for p in reqs}
        try:
            fn(**kwargs)
        except Exception as e:                       # noqa: BLE001 - classifying, not handling
            if "is required" in str(e):
                found.append((tool, param))
    return found


def test_some_tools_do_guard_their_own_arguments():
    """Without this the case below is parametrised over an empty list and passes by
    describing nothing - the failure mode that made the filter census decorative (#103)."""
    assert len(guarded()) >= 18, f"only {len(guarded())} tools guard their own arguments"


@pytest.mark.parametrize("tool, param", guarded(),
                         ids=lambda v: v if isinstance(v, str) else v)
def test_whitespace_is_not_a_value_either(tool, param):
    """`"   "` satisfies every guard written `if not x:` and none written
    `if not x.strip():`, and all twenty-one of these were the first kind (#104). A caller
    sending a space has made the same mistake as one sending nothing.

    `set_student_password`'s `password` is the one required string this property would be
    WRONG for - three spaces is a valid, if terrible, password, so whitespace there is
    content rather than formatting. It is absent from `guarded()` on its own, without being
    listed as an exception, because it carries a minimum-length rule instead of an
    is-required one and so never produces the message membership is measured by. Worth
    saying out loud rather than leaving to luck: if that rule ever became `if not password`,
    this census would start demanding the wrong thing."""
    fn = tools()[0][tool]
    reqs = [p for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty]
    kwargs = {p.name: ("   " if p.name == param else placeholder(p)) for p in reqs}
    with pytest.raises(ToolError, match="is required"):
        fn(**kwargs)
