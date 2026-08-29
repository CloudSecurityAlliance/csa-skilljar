"""Labels, tags and group categories — three similar things that are not the same."""
import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.taxonomy import register_taxonomy_tools
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

LABELS = [{"id": "l1", "name": "Needs review"}, {"id": "l2", "name": "2026 refresh"}]
TAGS = [{"id": "t1", "name": "Cloud Security", "slug": "cloud-security"}]
CATEGORIES = [{"id": "gc1", "name": "Partners"}]
COURSE_LABELS = {"c1": [{"id": "l1", "name": "Needs review"}]}


def build(profile="full", with_v1=True):
    policy = Policy.from_profile(profile)
    v1 = PolicyBackend(FakeV1Backend(labels=LABELS, tags=TAGS,
                                     group_categories=CATEGORIES,
                                     course_labels=COURSE_LABELS), policy) \
        if with_v1 else None
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy), v1=v1)
    app = MCPServer(name="t")
    register_taxonomy_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- the distinction that matters -------------------------------------------------------

def test_labels_are_internal_and_say_so(tools):
    """Describing an internal label as something learners browse is wrong in a way that
    is hard to spot from the data alone - both are just a name."""
    doc = inspect.getdoc(tools["list_labels"]) or ""
    assert "INTERNAL" in doc
    assert "not shown to learners" in doc
    assert "INTERNAL" in tools["list_labels"]()["note"]


def test_tags_are_public_and_carry_a_slug(tools):
    """The slug is the tell: it appears in catalogue URLs, so a tag is part of the
    customer-facing site in a way a label is not."""
    row = tools["list_tags"]()["rows"][0]
    assert row["slug"] == "cloud-security"
    doc = inspect.getdoc(tools["list_tags"]) or ""
    assert "PUBLIC" in doc
    assert "slug" in doc


def test_each_points_at_the_other(tools):
    """A reader holding one description must be able to tell it is not the other."""
    assert "list_tags" in (inspect.getdoc(tools["list_labels"]) or "")
    assert "list_labels" in (inspect.getdoc(tools["list_tags"]) or "")


def test_labels_have_no_slug_because_they_are_not_addressable(tools):
    assert "slug" not in tools["list_labels"]()["rows"][0]


# --- labels attach to content, not to a publication ----------------------------------------

def test_course_labels_are_the_same_on_every_domain(tools):
    out = tools["list_course_labels"](course_id="c1")
    assert [r["name"] for r in out["rows"]] == ["Needs review"]
    assert "same on\n" in out["note"] or "same on every domain" in out["note"]


def test_course_labels_want_a_course_not_a_published_course(tools):
    with pytest.raises(ToolError) as e:
        tools["list_course_labels"](course_id="")
    assert "not a published course" in str(e.value)


# --- group categories are the odd one out ----------------------------------------------------

def test_group_categories_organise_groups_not_content(tools):
    doc = inspect.getdoc(tools["list_group_categories"]) or ""
    assert "groups GROUPS, not content" in doc
    assert "filter_category_id" in doc


def test_group_categories_are_gated_with_the_group_tools():
    """They categorise student groups, so they belong to the capability that reads the
    groups themselves rather than to content.read."""
    tools = build(profile="authoring")     # content.read but no groups.read
    tools["list_labels"]()                 # content taxonomy: allowed
    with pytest.raises(ToolError) as e:
        tools["list_group_categories"]()
    assert "groups.read" in str(e.value)


# --- ordinary --------------------------------------------------------------------------------

def test_totals_are_surfaced(tools):
    assert tools["list_labels"]()["total"] == 2


def test_without_a_v1_key_the_error_names_the_variable():
    with pytest.raises(ToolError) as e:
        build(with_v1=False)["list_tags"]()
    assert "CSA_SKILLJAR_V1_API_KEY" in str(e.value)
