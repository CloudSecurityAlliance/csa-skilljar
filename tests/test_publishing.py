import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.publishing import register_publishing_tools
from csa_skilljar.policy import Policy, PolicyBackend

PUBLISHED = [
    {"type": "published-courses", "id": "pc1",
     "attributes": {"slug": "zero-trust-foundations", "live": True,
                    "open_access": False, "visible_on_catalog": False,
                    "require_all_prerequisites": True,
                    "unique_progress_per_enrollment": True,
                    "access_period_ends_at": "2026-12-31T00:00:00Z",
                    "created_at": "2026-01-01T00:00:00Z",
                    "modified_at": "2026-02-01T00:00:00Z"},
     "relationships": {"course": {"data": {"type": "courses", "id": "c1"}},
                       "domain": {"data": {"type": "domains", "id": "d1"}}}},
    {"type": "published-courses", "id": "pc2",
     "attributes": {"slug": None, "live": False},
     "relationships": {"course": {"data": {"type": "courses", "id": "c2"}},
                       "domain": {"data": {"type": "domains", "id": "d1"}}}},
]
DOMAINS = [
    {"type": "domains", "id": "d1", "attributes": {
        "name": "learn.example.org", "access": "PUBLIC", "require_https": True,
        "marketing_message": "Welcome", "modified_at": "2026-02-01T00:00:00Z"}},
    {"type": "domains", "id": "d2", "attributes": {
        "name": "private.example.org", "access": "PRIVATE_CODE"}},
]


def build(profile="full"):
    fake = FakeBackend(published_courses=list(PUBLISHED), domains=list(DOMAINS))
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_publishing_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, fake


@pytest.fixture
def tools():
    return build()[0]


# --- trap 3: create-only fields (ADR-008) --------------------------------------------

def test_update_rejects_create_only_fields(tools):
    """Skilljar ACCEPTS slug/course/domain on update and silently ignores them. ADR-008
    says refuse what upstream ignores, so the caller learns the change did not happen
    instead of believing it did."""
    for field, value in (("slug", "new-slug"), ("course_id", "c9"), ("domain_id", "d9")):
        with pytest.raises(ToolError) as e:
            tools["update_published_courses"](
                published_courses=[{"id": "pc1", field: value}])
        assert field in str(e.value)
        assert "silently ignores" in str(e.value)


def test_slug_is_settable_at_publish_time(tools):
    out = tools["publish_courses"](published_courses=[
        {"course_id": "c9", "domain_id": "d2", "slug": "brand-new-course"}])
    assert out["succeeded"] == 1


def test_update_still_accepts_the_ordinary_fields(tools):
    out = tools["update_published_courses"](
        published_courses=[{"id": "pc1", "open_access": True}])
    assert out["succeeded"] == 1
    assert tools["get_published_course"](id="pc1")["open_access"] is True


def test_update_needs_something_to_change(tools):
    with pytest.raises(ToolError) as e:
        tools["update_published_courses"](published_courses=[{"id": "pc1"}])
    assert "nothing to change" in str(e.value)


# --- trap 4: two booleans default true ------------------------------------------------

def test_the_two_true_defaults_are_documented(tools):
    """Ten of twelve booleans default false. These two do not, and a model that assumes
    uniformity gets the opposite of what it intended."""
    doc = inspect.getdoc(tools["publish_courses"]) or ""
    assert "require_all_prerequisites" in doc and "unique_progress_per_enrollment" in doc
    assert "DEFAULT FALSE, BUT TWO DEFAULT TRUE" in doc.upper()


def test_publish_warns_about_anonymous_access(tools):
    doc = inspect.getdoc(tools["publish_courses"]) or ""
    assert "ANONYMOUS" in doc


# --- trap 8: duplicate publish is per-item --------------------------------------------

def test_duplicate_publish_is_a_per_item_conflict(tools):
    """The rest of the batch still lands, so aborting on a 207 loses real work."""
    out = tools["publish_courses"](published_courses=[
        {"course_id": "c1", "domain_id": "d1"},        # already published
        {"course_id": "c7", "domain_id": "d1"}])       # fine
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "already_published"
    assert out["total"] == 2


def test_publish_requires_both_ends_of_the_join(tools):
    for missing in ("course_id", "domain_id"):
        item = {"course_id": "c9", "domain_id": "d9"}
        del item[missing]
        with pytest.raises(ToolError) as e:
            tools["publish_courses"](published_courses=[item])
        assert missing in str(e.value)


def test_unknown_publish_attribute_is_refused(tools):
    with pytest.raises(ToolError) as e:
        tools["publish_courses"](published_courses=[
            {"course_id": "c9", "domain_id": "d9", "is_public": True}])
    assert "is_public" in str(e.value)


def test_visibility_override_type_is_an_enum(tools):
    with pytest.raises(ToolError) as e:
        tools["publish_courses"](published_courses=[
            {"course_id": "c9", "domain_id": "d9", "visibility_override_type": "TEAM"}])
    assert "GROUP" in str(e.value)


# --- trap 1: the slug moves -----------------------------------------------------------

def test_unpublish_frees_the_slug():
    tools, _ = build()
    out = tools["unpublish_published_course"](id="pc1")
    assert out["live"] is False
    assert out["slug"] is None


def test_unpublish_republish_can_change_the_slug():
    """The slug is REASSIGNED on republish, not restored. A course can come back at a
    different public URL and nothing else announces it."""
    tools, _ = build()
    before = tools["get_published_course"](id="pc1")["slug"]
    tools["unpublish_published_course"](id="pc1")
    after = tools["republish_published_course"](id="pc1")
    assert after["live"] is True
    assert after["slug"] != before


def test_republish_description_warns_the_url_may_differ(tools):
    doc = inspect.getdoc(tools["republish_published_course"]) or ""
    assert "REASSIGNS" in doc
    assert "PUBLIC URL WILL BE DIFFERENT" in doc


# --- trap 2: delete is an unpublish ---------------------------------------------------

def test_delete_published_course_is_a_soft_unpublish():
    tools, fake = build()
    tools["delete_published_course"](id="pc1")
    assert tools["get_published_course"](id="pc1")["live"] is False
    assert len(fake._published) == 2          # nothing was destroyed


def test_delete_and_unpublish_descriptions_disambiguate(tools):
    """Two tools, near-identical behaviour. Each must point at the other so a model is
    not left guessing which one the caller meant."""
    delete = inspect.getdoc(tools["delete_published_course"]) or ""
    unpublish = inspect.getdoc(tools["unpublish_published_course"]) or ""
    assert "SOFT UNPUBLISH, NOT A DELETION" in delete
    assert "unpublish_published_course" in delete
    assert "prefer that one" in delete
    assert "delete_published_course" in unpublish


# --- reads ----------------------------------------------------------------------------

def test_listing_includes_unpublished_rows_by_default(tools):
    ids = [p["id"] for p in tools["list_published_courses"]()["published_courses"]]
    assert ids == ["pc1", "pc2"]


def test_filter_live(tools):
    ids = [p["id"] for p in
           tools["list_published_courses"](filter_live=True)["published_courses"]]
    assert ids == ["pc1"]


def test_list_warns_that_unpublished_rows_are_included(tools):
    doc = inspect.getdoc(tools["list_published_courses"]) or ""
    assert "BOTH LIVE AND UNPUBLISHED" in doc


def test_published_course_carries_both_relationship_ids(tools):
    pc = tools["get_published_course"](id="pc1")
    assert pc["course_id"] == "c1"
    assert pc["domain_id"] == "d1"


def test_get_published_course_distinguishes_the_two_id_kinds(tools):
    doc = inspect.getdoc(tools["get_published_course"]) or ""
    assert "NOT the course id" in doc


# --- domains --------------------------------------------------------------------------

def test_domain_name_filter_is_exact(tools):
    assert [d["id"] for d in
            tools["list_domains"](filter_name="learn.example.org")["domains"]] == ["d1"]
    assert tools["list_domains"](filter_name="learn")["domains"] == []


def test_filter_domains_by_access(tools):
    assert [d["id"] for d in
            tools["list_domains"](filter_access="PRIVATE_CODE")["domains"]] == ["d2"]


def test_get_domain(tools):
    assert tools["get_domain"](id="d1")["name"] == "learn.example.org"


def test_domains_are_read_only_here(tools):
    for name in ("list_domains", "get_domain"):
        assert "read-only" in (inspect.getdoc(tools[name]) or "")


# --- capability separation ------------------------------------------------------------

def test_authoring_cannot_publish():
    """The point of a separate publishing.write: a credential that can write lesson HTML
    must not be able to put it in front of the public."""
    tools, _ = build(profile="authoring")
    with pytest.raises(ToolError) as e:
        tools["publish_courses"](published_courses=[
            {"course_id": "c9", "domain_id": "d1"}])
    assert "publishing.write" in str(e.value)


def test_parity_can_read_the_catalog_but_not_change_it():
    tools, _ = build(profile="parity")
    assert tools["list_domains"]()["domains"]
    with pytest.raises(ToolError):
        tools["unpublish_published_course"](id="pc1")
