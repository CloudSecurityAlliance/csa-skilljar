"""Student groups and their memberships.

Groups are how Skilljar decides who can see which courses, so these tools sit between
content administration and learner administration and are gated by neither. They get
their own `groups.*` capabilities.

Three behaviours here are unusual enough that getting them wrong is silent:

* `updated_at`, not `modified_at`. Groups are one of only two v2 resources spelled this
  way; the other twelve use `modified_at`.
* An explicitly-null `category_id` CLEARS the category. Omitting the key leaves it alone.
  "Not provided" and "provided as null" are different requests.
* `rule_email_domains` REPLACES the stored array rather than merging into it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import (
    BatchResultOut,
    GroupListOut,
    GroupOut,
    MembershipResultOut,
    VisibilityOverrideListOut,
    VisibilityOverrideOut,
)
from ._base import DESTRUCTIVE, IDEMPOTENT_WRITE, READ, WRITE, translate_errors

# `updated_at` is deliberate. See the module docstring; a "correction" to modified_at
# drops the field from every response with no error anywhere.
_GROUP_KEYS = ("name", "rule_email_domains", "send_course_enrollment_email",
               "category_id", "created_at", "updated_at")
_CREATE_FIELDS = frozenset({"name", "category_id", "rule_email_domains",
                            "send_course_enrollment_email"})
_UPDATE_FIELDS = _CREATE_FIELDS
_MAX_NAME = 100

_NOTE = ("Results are one page. When has_more is true, call again with next_cursor. "
         "The official Skilljar MCP server cannot page at all; page_cursor and page_size "
         "are extensions here.")
_BATCH_NOTE = ("Rows are processed independently. A non-empty `failed` means some rows "
               "did not land - report that rather than reporting success.")
# `updated_at`, not `modified_at` - the same spelling as GroupAttributes, and the only
# other v2 resource that does it. See tests/test_groups.py.
_OVERRIDE_KEYS = ("published_course_id", "is_visible", "created_at", "updated_at")
_COEXIST_NOTE = ("The unique key includes is_visible, so an allow row and a block row "
                 "for the SAME course can both exist. Skilljar's guidance is to pick "
                 "one; if both are present the behaviour is not defined here.")
_MEMBER_NOTE = ("This call is idempotent: success does NOT mean anything changed. "
                "Adding an existing member succeeds, and removing someone who was never "
                "a member also succeeds. The result cannot be used to test membership.")


def _batch_out(envelope: dict[str, Any]) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]], "note": _BATCH_NOTE}


def _flatten(row: dict[str, Any]) -> GroupOut:
    attrs = row.get("attributes", {})
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in _GROUP_KEYS:
        if key in attrs:
            out[key] = attrs[key]
    return cast(GroupOut, out)


def _check_group_attrs(attrs: dict[str, Any], where: str, allowed: frozenset[str],
                       *, require_name: bool) -> None:
    if not isinstance(attrs, dict):
        raise ValueError(f"{where} must be an object of attributes")
    unknown = sorted(set(attrs) - allowed - {"id"})
    if unknown:
        raise ValueError(f"{where} has unknown attribute(s) {', '.join(unknown)}. "
                         f"Allowed: {', '.join(sorted(allowed))}")
    if require_name and not attrs.get("name"):
        raise ValueError(f"{where} needs a name")
    name = attrs.get("name")
    if name is not None and not 1 <= len(str(name)) <= _MAX_NAME:
        raise ValueError(f"{where} name must be 1 to {_MAX_NAME} characters")
    domains = attrs.get("rule_email_domains")
    if domains is not None:
        if not isinstance(domains, list):
            raise ValueError(f"{where} rule_email_domains must be a list of bare domains")
        for d in domains:
            if "@" in str(d):
                raise ValueError(
                    f"{where} rule_email_domains takes bare domains like example.com, "
                    f"not {d!r}")


def _flatten_override(row: dict[str, Any]) -> VisibilityOverrideOut:
    attrs = row.get("attributes", {})
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in _OVERRIDE_KEYS:
        if key in attrs:
            out[key] = attrs[key]
    return cast(VisibilityOverrideOut, out)


def _check_overrides(items: list[dict[str, Any]], where: str) -> None:
    if not items:
        raise ValueError(f"{where} must contain at least one item")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{where}[{i}] must be an object")
        unknown = sorted(set(item) - {"published_course_id", "is_visible"})
        if unknown:
            raise ValueError(f"{where}[{i}] has unknown key(s) {', '.join(unknown)}. "
                             f"Allowed: published_course_id, is_visible")
        if not item.get("published_course_id"):
            raise ValueError(f"{where}[{i}] needs a published_course_id - the "
                             f"published-course id, not the course id")


def _member_ids(where: str, student_ids: list[str]) -> None:
    if not student_ids:
        raise ValueError(f"{where} must contain at least one student id")
    for i, sid in enumerate(student_ids):
        if not isinstance(sid, str) or not sid:
            raise ValueError(f"{where}[{i}] must be a non-empty student id string")


def register_group_tools(app: MCPServer,
                         get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_groups(filter_name: str | None = None, filter_category_id: str | None = None,
                    page_cursor: str | None = None,
                    page_size: int | None = None) -> GroupListOut:
        """List student groups, one page at a time.

        Group membership drives which published courses a learner can see, so this is
        the starting point for any "who can access what" question. Results are one page:
        when has_more is true, call again with next_cursor.

        `filter_name` is a case-INSENSITIVE substring match. Note that group names
        themselves are case-SENSITIVE and unique, so "Staff" and "staff" can both exist
        and this filter will return both.

        `filter_category_id` takes an obfuscated StudentGroupCategory id. An unknown or
        cross-organization id returns zero results rather than an error, so an empty
        list here does not prove the category does not exist.

        Each group carries `updated_at` - most other Skilljar objects call this field
        `modified_at`.

        Requires the `student-groups:read` OAuth scope.
        """
        envelope = get_client().list_groups(
            name=filter_name, category_id=filter_category_id,
            cursor=page_cursor, page_size=page_size)
        rows = envelope.get("data", [])
        meta = envelope.get("meta", {})
        out: GroupListOut = {"groups": [_flatten(r) for r in rows],
                             "has_more": bool(meta.get("has_more")), "note": _NOTE}
        if meta.get("next_cursor"):
            out["next_cursor"] = str(meta["next_cursor"])
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_group(id: str) -> GroupOut:
        """Fetch one student group by its obfuscated id.

        Returns the group's name, its auto-add email-domain rules, its category and its
        timestamps. It does NOT return the member list - v2 has no endpoint that reads
        memberships back, only `add_group_memberships` and `remove_group_memberships`
        that change them.

        The last-changed timestamp is `updated_at`, not `modified_at`.

        Requires the `student-groups:read` OAuth scope.
        """
        return _flatten(get_client().get_group(group_id=id)["data"])

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_groups(groups: list[dict[str, Any]]) -> BatchResultOut:
        """Create student groups. This is a BATCH operation.

        Each item needs a `name` of 1 to 100 characters, UNIQUE within the organization
        and CASE-SENSITIVE - "Partners" and "partners" are two different groups, which
        is a good way to end up with an accidental duplicate.

        Optional per item:
          `category_id`                    obfuscated StudentGroupCategory id, which must
                                           belong to this organization or the row fails
          `rule_email_domains`             bare domains like example.com (no @) that
                                           auto-add learners to this group when they
                                           sign up; duplicates are collapsed
          `send_course_enrollment_email`   whether members get enrollment email

        Within one batch, the first item to claim a name wins and later ones fail.

        Requires the `student-groups:write` OAuth scope.
        """
        if not groups:
            raise ValueError("groups must contain at least one item")
        for i, attrs in enumerate(groups):
            _check_group_attrs(attrs, f"groups[{i}]", _CREATE_FIELDS, require_name=True)
        return _batch_out(get_client().create_groups(items=groups))

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_groups(groups: list[dict[str, Any]]) -> BatchResultOut:
        """Change student groups. This is a BATCH operation.

        Every item needs an `id`. Groups have no stable natural key - names are
        renameable, so a name is not durable enough to identify one across calls.

        TWO BEHAVIOURS THAT LOSE DATA IF YOU ASSUME THE OPPOSITE:

        `rule_email_domains` REPLACES the whole stored array. It does not merge. To add
        one domain, send every existing domain plus the new one; sending only the new one
        deletes the rest.

        `category_id: null` CLEARS the category. Omitting the key leaves it unchanged.
        These are different requests, so do not send an explicit null unless you mean
        "remove this group from its category".

        At least one changeable field per item is required.

        Requires the `student-groups:write` OAuth scope.
        """
        if not groups:
            raise ValueError("groups must contain at least one item")
        for i, attrs in enumerate(groups):
            where = f"groups[{i}]"
            _check_group_attrs(attrs, where, _UPDATE_FIELDS, require_name=False)
            if not attrs.get("id"):
                raise ValueError(
                    f"{where} needs an `id`. Group names are renameable, so they cannot "
                    f"identify a group across calls.")
            # Key PRESENCE, not truthiness: `category_id: None` is a real instruction to
            # clear the category, and a falsy check would reject it as "no fields given".
            if not set(attrs) & _UPDATE_FIELDS:
                raise ValueError(
                    f"{where} has an id but nothing to change. Send at least one of "
                    f"{', '.join(sorted(_UPDATE_FIELDS))}.")
        return _batch_out(get_client().update_groups(items=groups))

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def delete_groups(group_ids: list[str]) -> BatchResultOut:
        """Delete student groups. THIS IS A HARD DELETE AND IT CASCADES.

        Unlike quizzes and question banks, a group is not soft-deleted. It is removed
        from the database, and everything that points at it goes too:

          * every membership - learners are removed from the group
          * every published-course visibility override granted through this group, which
            means learners can LOSE ACCESS TO COURSES they can currently see
          * other link rows referencing the group

        The learners themselves are not deleted, and their enrollments survive. What is
        lost is the access this group was granting.

        `group_ids` takes the obfuscated ids of the groups to destroy; every id is
        processed independently and a `failed` entry means that group still exists.

        There is no undo. If the intent is to stop using a group while keeping the
        option to restore it, rename it and clear its `rule_email_domains` instead.

        Requires the `student-groups:write` OAuth scope.
        """
        if not group_ids:
            raise ValueError("group_ids must contain at least one id")
        return _batch_out(get_client().delete_groups(group_ids=group_ids))

    @app.tool(annotations=IDEMPOTENT_WRITE)
    @translate_errors
    def add_group_memberships(id: str, student_ids: list[str]) -> MembershipResultOut:
        """Add learners to a student group. This is a BATCH operation.

        `id` is the group. `student_ids` are obfuscated learner ids.

        IDEMPOTENT: adding someone who is already a member succeeds and reports them as
        added. There is no "already a member" outcome, so a success here does not tell
        you the group changed. Duplicates inside one batch are first-wins; the later
        copies fail as `duplicate_in_batch`.

        An unknown group is a not-found error regardless of what else is in the request,
        so a failure here does not distinguish a bad group id from bad learner ids.

        Adding a learner to a group can GRANT COURSE ACCESS, because visibility overrides
        are attached to groups.

        Requires the `student-groups:write` OAuth scope.
        """
        _member_ids("student_ids", student_ids)
        parsed = parse_batch(get_client().add_group_memberships(
            group_id=id, student_ids=student_ids))
        return {"group_id": id, "total": parsed["total"],
                "succeeded": len(parsed["succeeded"]), "failed": parsed["failed"],
                "student_ids": [s.get("id", "") for s in parsed["succeeded"]],
                "note": _MEMBER_NOTE}

    @app.tool(annotations=IDEMPOTENT_WRITE)
    @translate_errors
    def remove_group_memberships(id: str, student_ids: list[str]) -> MembershipResultOut:
        """Remove learners from a student group. This is a BATCH operation.

        `id` is the group. `student_ids` are obfuscated learner ids.

        IDEMPOTENT: removing someone who was never a member reports `deleted` just like
        removing a real member. There is no "not a member" outcome on the wire, so this
        call cannot be used to find out who was in the group.

        Removing a learner can REVOKE COURSE ACCESS they currently have, if the group
        carried a visibility override. Their enrollments and progress are untouched.

        Requires the `student-groups:write` OAuth scope.
        """
        _member_ids("student_ids", student_ids)
        parsed = parse_batch(get_client().remove_group_memberships(
            group_id=id, student_ids=student_ids))
        return {"group_id": id, "total": parsed["total"],
                "succeeded": len(parsed["succeeded"]), "failed": parsed["failed"],
                "student_ids": [s.get("id", "") for s in parsed["succeeded"]],
                "note": _MEMBER_NOTE}

    @app.tool(annotations=READ)
    @translate_errors
    def list_visibility_overrides(id: str, filter_is_visible: bool | None = None,
                                  filter_published_course_id: str | None = None,
                                  page_cursor: str | None = None,
                                  page_size: int | None = None
                                  ) -> VisibilityOverrideListOut:
        """List one group's course-visibility overrides, one page at a time.

        `id` is the GROUP id. Overrides hang off the group, not off the course - which
        is the opposite of Skilljar's v1 API, where visibility hangs off the content.
        Results are one page: when has_more is true, call again with next_cursor.

        Each row says: for this group, show (`is_visible` true, an allowlist entry) or
        hide (`is_visible` false, a blocklist entry) one published course, overriding
        that course's own default.

        An unknown group is a not-found error, which is a different answer from an
        empty list. An empty list means the group exists and has no overrides.

        Rows carry `updated_at`, not `modified_at`.

        Requires the `student-groups:read` OAuth scope.
        """
        envelope = get_client().list_visibility_overrides(
            group_id=id, is_visible=filter_is_visible,
            published_course_id=filter_published_course_id,
            cursor=page_cursor, page_size=page_size)
        rows = envelope.get("data", [])
        meta = envelope.get("meta", {})
        out: VisibilityOverrideListOut = {
            "group_id": id, "overrides": [_flatten_override(r) for r in rows],
            "has_more": bool(meta.get("has_more")),
            "note": f"{_NOTE} {_COEXIST_NOTE}"}
        if meta.get("next_cursor"):
            out["next_cursor"] = str(meta["next_cursor"])
        return out

    @app.tool(annotations=WRITE)
    @translate_errors
    def add_visibility_overrides(id: str,
                                 overrides: list[dict[str, Any]]) -> BatchResultOut:
        """Grant or deny a group access to published courses. This is a BATCH operation.

        `id` is the GROUP id. `overrides` is the batch: each item needs
        `published_course_id` - the
        published-course id, not the course id - and may set `is_visible`:

          `is_visible: true`  (the DEFAULT) an ALLOWLIST entry: members see the course
                              even though it is hidden by default
          `is_visible: false` a BLOCKLIST entry: members do NOT see the course even
                              though it is visible by default

        THE UNIQUE KEY INCLUDES `is_visible`, so adding true and then false for the same
        course creates TWO rows that contradict each other rather than the second
        replacing the first. Remove the one you do not want; Skilljar's own guidance is
        to keep only one.

        Idempotent: re-adding an identical override succeeds and changes nothing, so a
        success here does not mean access changed. Duplicates within one batch are
        first-wins.

        An unknown group is a not-found error whatever else is in the request.

        Requires the `student-groups:write` OAuth scope.
        """
        _check_overrides(overrides, "overrides")
        return _batch_out(get_client().add_visibility_overrides(
            group_id=id, items=overrides))

    @app.tool(annotations=WRITE)
    @translate_errors
    def remove_visibility_overrides(id: str,
                                    overrides: list[dict[str, Any]]) -> BatchResultOut:
        """Remove a group's course-visibility overrides. This is a BATCH operation.

        `id` is the GROUP id. `overrides` is the batch, and each item identifies one by
        `published_course_id` plus `is_visible` - because both an allow row and a block
        row can exist for the same course, `is_visible` says WHICH ONE to remove. It
        defaults to true, so an unqualified removal takes out the allowlist entry and
        leaves any blocklist entry in place.

        Removing an allowlist entry can REVOKE ACCESS the group currently has. Removing
        a blocklist entry can GRANT access it currently lacks. Neither is announced
        anywhere else.

        The returned ids echo the `published_course_id` you sent, NOT the override's own
        id, so results line up with the request without a second lookup.

        Removing an override that does not exist succeeds - like the membership tools,
        this cannot be used to test what is there.

        Requires the `student-groups:write` OAuth scope.
        """
        _check_overrides(overrides, "overrides")
        return _batch_out(get_client().remove_visibility_overrides(
            group_id=id, items=overrides))
