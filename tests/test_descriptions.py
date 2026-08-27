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
