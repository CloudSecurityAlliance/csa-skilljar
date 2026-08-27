# Block 7 — Groups & signup fields — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Eleven tools over student groups, their memberships, and the signup-field answers
learners give at registration.

**Architecture:** Two families that look routine and are not. Groups introduce
*explicit-null-means-clear* and a hard cascading delete; signup-field values introduce a hybrid
envelope, an upsert wearing a `create_` name, and two different identifiers for the same
conceptual row.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · Contracts:
[`specs/official-mcp/`](../../../specs/official-mcp/) · v2 OpenAPI: `specs/skilljar-v2-openapi.json`

## Global Constraints

Unchanged from Blocks 2–6.

---

## The seven traps, and where each one is pinned

Every row here is a place where a reasonable implementation is wrong. Each gets a named
regression test, and the ones that fail silently get a mutation.

| # | Trap | Fails how | Pinned by |
|---|---|---|---|
| 1 | `GroupAttributes` uses `updated_at`; twelve of fourteen v2 schemas use `modified_at` | **Silently.** The key is absent from the flatten allowlist, the field vanishes from output, group sync sees every group as never-updated | `test_groups_expose_updated_at_not_modified_at` |
| 2 | `update_groups`: `category_id: null` **clears** the assignment; omitting it leaves it alone | **Silently.** Treat null as absent and a caller who meant "uncategorise" gets a no-op and no error | `test_explicit_null_category_clears_and_omitted_does_not` |
| 3 | `update_groups`: `rule_email_domains` **replaces** the whole array | **Destructively.** A caller who thinks it merges deletes their other domain rules | description + `test_rule_email_domains_replaces_the_array` |
| 4 | `delete_groups` is a **hard** delete — `StudentGroup` is not a `SoftDeletionModel`; memberships and visibility overrides cascade at the database | Loudly for the group, silently for everything hanging off it | description; `test_delete_groups_description_names_the_cascade` |
| 5 | `get_signup_field_value`'s parameter is `signup_field_value_id`, **not** `id` | Loudly, but only against the real API | `test_get_signup_field_value_parameter_is_not_id` |
| 6 | `create_signup_field_values` keys items by the signup-**field** id; `update_` keys them by the signup-field-**value** id | **Silently or as a 404.** Same conceptual row, two identifiers | both descriptions; `test_the_two_signup_field_id_meanings_are_documented` |
| 7 | `create_signup_field_values` is an **upsert** and uses a hybrid envelope (`student_id` at top level, items in `data`) | Silently overwrites an existing answer | description + `test_create_signup_field_values_sends_the_hybrid_envelope` |

### A finding the ROADMAP gets wrong

ROADMAP says to watch `GroupAttributes.updated_at` as the lone inconsistency. Surveying all
fourteen `*Attributes` schemas in the v2 spec, **two** use `updated_at`: `GroupAttributes` and
`VisibilityOverrideAttributes`. The second is a Block 8 tool (`list_visibility_overrides`).

Both exceptions are group-adjacent. Fix the ROADMAP as part of this block so Block 8 is not
misled, and note it in the changelog.

`backend.py` has three `updated_since` filters that hardcode `modified_at`. `GroupFilters`
declares no such filter, so groups never reach that code — pinned by
`test_group_listing_has_no_updated_since_filter` rather than left to observation.

---

## Files

- Create: `src/csa_skilljar/mcp/_tools/groups.py` (7 tools)
- Create: `src/csa_skilljar/mcp/_tools/signup_fields.py` (4 tools)
- Create: `tests/test_groups.py`, `tests/test_signup_fields.py`
- Modify: `src/csa_skilljar/backend.py` (Protocol, FakeBackend, V2Backend — 11 methods)
- Modify: `src/csa_skilljar/mcp/_schemas.py` (`GroupOut`, `SignupFieldValueOut`)
- Modify: `src/csa_skilljar/policy.py` (`_GATES` × 11; new `WRITE_GROUPS`, `DELETE_GROUPS`)
- Modify: `src/csa_skilljar/mcp/server.py`, `_tools/__init__.py`
- Modify: `tests/test_protocol.py` (EXERCISE × 11), `tests/test_policy.py`,
  `tests/test_descriptions.py` (REQUIREMENTS × 11)
- Modify: `README.md` (→ 58 tools), `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`

## Capabilities

Groups are a **content-shaped** resource that gates **people-shaped** access: group membership
drives course visibility. Neither `content.*` nor `people.*` is right, so:

- `groups.read` — `list_groups`, `get_group`, `list_signup_field_values`,
  `get_signup_field_value`
- `groups.write` — `create_groups`, `update_groups`, `add_group_memberships`,
  `remove_group_memberships`, `create_signup_field_values`, `update_signup_field_values`
- `groups.delete` — `delete_groups` alone, because of trap 4's cascade

Mirrors the `content.write` / `content.delete` split from Block 3. `groups.delete` goes in no
profile but `full`.

**Signup-field values are learner-submitted free text** — the same attacker-influencable surface
as lesson HTML. `list_signup_field_values` must say so, as `list_course_ratings` does.

---

## Membership semantics — reproduce exactly, do not "improve"

From the captured registry, both are **idempotent**:

- `add_group_memberships` on an existing member returns it as `succeeded`. There is no
  `already_a_member` error code.
- `remove_group_memberships` on a non-member returns status `deleted`. There is no
  `not_a_member` outcome on the wire.
- Duplicates within one batch are first-wins; later ones are pre-marked `duplicate_in_batch`.
- The group lookup runs **before** the envelope guard, so a missing group is 404 regardless of
  body content. Deliberate — it stops a caller inferring group existence from the 400-vs-404
  boundary. Preserve it; `test_missing_group_is_404_even_with_a_malformed_body` names it.
- Items are `{type: "students", id}` with **extra keys forbidden** — a stray `attributes` block
  copied from `POST /v2/students/` must 422, not silently no-op.

A tool description that promises "tells you who was already a member" would be a lie. Say what
the wire says: the call is idempotent and success does not imply a change occurred.

---

## Task sequence

Each task is TDD against `FakeBackend`, ends green, and commits.

- [ ] **Task 1 — Group reads.** `list_groups` (filters `name`, `category_id`; cursor
      pagination), `get_group`. Traps 1 and the no-`updated_since` pin.
- [ ] **Task 2 — Group writes.** `create_groups`, `update_groups`. Traps 2 and 3. The
      explicit-null sentinel is the whole of Task 2's difficulty.
- [ ] **Task 3 — Group delete.** `delete_groups` behind `groups.delete`. Trap 4.
- [ ] **Task 4 — Memberships.** `add_group_memberships`, `remove_group_memberships`.
      Idempotence, first-wins, the 404-before-guard ordering, `extra: forbid`.
- [ ] **Task 5 — Signup-field reads.** `list_signup_field_values` (filters `student.id`,
      `signup-field.id`, `domains`), `get_signup_field_value`. Traps 5 and the untrusted-text
      warning.
- [ ] **Task 6 — Signup-field writes.** `create_signup_field_values`,
      `update_signup_field_values`. Traps 6 and 7.
- [ ] **Task 7 — Mutations, docs, PR.** Mutate every guard in the table; fix the ROADMAP's
      `updated_at` claim; README/CHANGELOG/TODO; open the PR.

## Mutations required before the PR

| Mutation | Must be killed by |
|---|---|
| `_GROUP_KEYS` says `modified_at` | `test_groups_expose_updated_at_not_modified_at` |
| Explicit `category_id: null` treated as absent | `test_explicit_null_category_clears_and_omitted_does_not` |
| `delete_groups` gated by `groups.write` | policy matrix + per-profile refusal |
| `get_signup_field_value` parameter renamed to `id` | `test_get_signup_field_value_parameter_is_not_id` |
| `create_signup_field_values` sends `student_id` inside each item | `test_create_signup_field_values_sends_the_hybrid_envelope` |

**Ships:** v0.6.0 — still queued behind `WAITING-FOR-002`.
