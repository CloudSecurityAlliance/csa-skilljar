import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.groups import register_group_tools
from csa_skilljar.policy import Policy, PolicyBackend

# Note `updated_at`. Twelve of fourteen v2 attribute schemas use `modified_at`; groups
# and visibility overrides are the exceptions, and this fixture is the reminder.
GROUPS = [
    {"type": "groups", "id": "g1", "attributes": {
        "name": "Partners", "rule_email_domains": ["partner.example"],
        "category_id": "cat1", "send_course_enrollment_email": True,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z"}},
    {"type": "groups", "id": "g2", "attributes": {
        "name": "partners", "rule_email_domains": [], "category_id": None,
        "updated_at": "2026-03-01T00:00:00Z"}},
]
STUDENTS = [{"type": "students", "id": "s1", "attributes": {"email": "a@example.org"}},
            {"type": "students", "id": "s2", "attributes": {"email": "b@example.org"}}]


def build(profile="full"):
    fake = FakeBackend(groups=list(GROUPS), students=list(STUDENTS))
    client = SkilljarClient(PolicyBackend(fake, Policy.from_profile(profile)))
    app = MCPServer(name="t")
    register_group_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}, fake


@pytest.fixture
def tools():
    return build()[0]


# --- trap 1: the timestamp field name ------------------------------------------------

def test_groups_expose_updated_at_not_modified_at(tools):
    """v2 spells the group timestamp `updated_at`. Twelve other resources say
    `modified_at`, so a uniform assumption drops the field with no error at all - the
    group simply looks as though it has never been touched."""
    group = tools["get_group"](id="g1")
    assert group["updated_at"] == "2026-02-01T00:00:00Z"
    assert "modified_at" not in group


def test_group_listing_has_no_updated_since_filter():
    """backend.py filters courses, lessons and quizzes by a hardcoded `modified_at`.
    Groups must never reach that path, and the way to guarantee it is to have no
    updated_since parameter at all."""
    from csa_skilljar.backend import Backend
    params = inspect.signature(Backend.list_groups).parameters
    assert "updated_since" not in params


# --- reads ---------------------------------------------------------------------------

def test_name_filter_is_a_case_insensitive_substring(tools):
    """The FILTER ignores case even though group NAMES are case-sensitive, so one
    filter legitimately returns two distinct groups."""
    got = [g["id"] for g in tools["list_groups"](filter_name="PARTNER")["groups"]]
    assert got == ["g1", "g2"]


def test_unknown_category_returns_empty_not_an_error(tools):
    out = tools["list_groups"](filter_category_id="nope")
    assert out["groups"] == []
    assert out["has_more"] is False


def test_get_group_does_not_claim_to_return_members(tools):
    assert "member" not in str(tools["get_group"](id="g1")).lower()


# --- trap 3: rule_email_domains replaces -------------------------------------------

def test_rule_email_domains_replaces_the_array(tools):
    tools["update_groups"](groups=[{"id": "g1", "rule_email_domains": ["new.example"]}])
    assert tools["get_group"](id="g1")["rule_email_domains"] == ["new.example"]


def test_bare_domains_only(tools):
    with pytest.raises(ToolError) as e:
        tools["create_groups"](groups=[{"name": "X",
                                        "rule_email_domains": ["a@b.example"]}])
    assert "bare domains" in str(e.value)


# --- trap 2: explicit null clears, omitted does not ---------------------------------

def test_explicit_null_category_clears_and_omitted_does_not(tools):
    """The whole of this block's subtlety. `category_id: None` is an instruction, not an
    absence, and the two must produce different writes."""
    tools["update_groups"](groups=[{"id": "g1", "name": "Renamed"}])
    assert tools["get_group"](id="g1")["category_id"] == "cat1"   # untouched

    tools["update_groups"](groups=[{"id": "g1", "category_id": None}])
    assert tools["get_group"](id="g1")["category_id"] is None     # cleared


def test_explicit_null_alone_counts_as_a_change(tools):
    """A truthiness check on the payload would reject this as 'nothing to change',
    which is exactly the silent failure trap 2 describes."""
    out = tools["update_groups"](groups=[{"id": "g1", "category_id": None}])
    assert out["succeeded"] == 1


def test_an_id_with_no_fields_is_refused(tools):
    with pytest.raises(ToolError) as e:
        tools["update_groups"](groups=[{"id": "g1"}])
    assert "nothing to change" in str(e.value)


def test_update_requires_an_id(tools):
    with pytest.raises(ToolError) as e:
        tools["update_groups"](groups=[{"name": "Partners"}])
    assert "renameable" in str(e.value)


# --- creation ------------------------------------------------------------------------

def test_names_are_case_sensitive_so_both_can_exist(tools):
    out = tools["create_groups"](groups=[{"name": "PARTNERS"}])
    assert out["succeeded"] == 1


def test_duplicate_name_is_first_wins(tools):
    out = tools["create_groups"](groups=[{"name": "New"}, {"name": "New"}])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "duplicate_in_batch"


def test_name_length_is_bounded(tools):
    with pytest.raises(ToolError) as e:
        tools["create_groups"](groups=[{"name": "x" * 101}])
    assert "100" in str(e.value)


def test_unknown_attribute_is_refused(tools):
    with pytest.raises(ToolError) as e:
        tools["create_groups"](groups=[{"name": "X", "colour": "red"}])
    assert "colour" in str(e.value)


# --- trap 4: the hard cascading delete ----------------------------------------------

def test_delete_groups_description_names_the_cascade(tools):
    doc = inspect.getdoc(tools["delete_groups"]) or ""
    assert "HARD DELETE" in doc
    assert "visibility" in doc.lower()
    assert "LOSE ACCESS" in doc


def test_delete_cascades_to_memberships():
    tools, fake = build()
    tools["add_group_memberships"](id="g1", student_ids=["s1"])
    assert fake.group_members("g1") == ["s1"]
    tools["delete_groups"](group_ids=["g1"])
    assert fake.group_members("g1") == []


def test_delete_is_gated_separately_from_write():
    tools, _ = build(profile="people")     # grants groups.read + groups.write
    tools["create_groups"](groups=[{"name": "Allowed"}])
    with pytest.raises(ToolError) as e:
        tools["delete_groups"](group_ids=["g1"])
    assert "groups.delete" in str(e.value)


# --- memberships ---------------------------------------------------------------------

def test_adding_an_existing_member_succeeds():
    """Idempotent per JSON:API. There is no already_a_member code, so success does not
    mean the group changed."""
    tools, fake = build()
    tools["add_group_memberships"](id="g1", student_ids=["s1"])
    out = tools["add_group_memberships"](id="g1", student_ids=["s1"])
    assert out["succeeded"] == 1
    assert out["failed"] == []
    assert fake.group_members("g1") == ["s1"]


def test_removing_a_non_member_reports_deleted():
    tools, _ = build()
    out = tools["remove_group_memberships"](id="g1", student_ids=["s2"])
    assert out["succeeded"] == 1
    assert out["failed"] == []


def test_membership_result_says_success_is_not_evidence_of_change(tools):
    out = tools["add_group_memberships"](id="g1", student_ids=["s1"])
    assert "cannot be used to test membership" in out["note"]


def test_duplicates_in_one_batch_are_first_wins(tools):
    out = tools["add_group_memberships"](id="g1", student_ids=["s1", "s1"])
    assert out["succeeded"] == 1
    assert out["failed"][0]["code"] == "duplicate_in_batch"


def test_missing_group_is_404_even_with_a_malformed_body(tools):
    """Upstream looks the group up BEFORE validating the envelope, so a caller cannot
    tell a bad group id from a bad body - deliberately, so group existence cannot be
    probed through the 400-vs-404 boundary. Preserve the ordering."""
    with pytest.raises(ToolError) as e:
        tools["add_group_memberships"](id="nope", student_ids=["s1"])
    assert "no group with id nope" in str(e.value)


def test_empty_membership_list_is_refused(tools):
    with pytest.raises(ToolError):
        tools["add_group_memberships"](id="g1", student_ids=[])


def test_membership_tools_are_annotated_idempotent():
    app = MCPServer(name="t")
    register_group_tools(app, lambda: None)
    for name in ("add_group_memberships", "remove_group_memberships"):
        assert app._tool_manager._tools[name].annotations.idempotent_hint is True
