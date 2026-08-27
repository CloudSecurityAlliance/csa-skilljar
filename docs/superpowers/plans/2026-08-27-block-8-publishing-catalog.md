# Block 8 — Publishing & catalog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Twelve tools that put a course in front of learners: publishing it to a domain,
controlling who can see it, and reading the catalog it lands in.

**Architecture:** Three families with three different owners. Published courses and domains get
a new `publishing.*` capability; visibility overrides join `groups.*` from Block 7, because
upstream gates them with `student-groups:*` and hangs them off the group.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · Contracts:
[`specs/official-mcp/`](../../../specs/official-mcp/) · v2 OpenAPI: `specs/skilljar-v2-openapi.json`

## Global Constraints

Unchanged from Blocks 2–7.

---

## This is the block where a mistake is visible to the public

Every other block so far has changed private state. These tools change what anonymous visitors
to a customer-facing website can see. `open_access` allows anonymous access; `visible_on_catalog`
puts a course in a public listing; `unpublish` takes a live URL away.

That shapes two decisions:

1. **`publishing.write` is its own capability, not part of `content.write`.** An authoring
   credential that can write lesson HTML must not be able to publish that lesson to the internet.
   `authoring` grants `content.read` + `content.write` and gets no publishing rights.
2. **Visibility overrides are gated by `groups.write`, not `publishing.write`.** Upstream hangs
   them off `/v2/groups/{id}/relationships/published-course-visibility/` and requires
   `student-groups:write`. Gating by what the credential actually needs keeps the local gate and
   the remote scope from disagreeing.

---

## The traps

| # | Trap | Fails how | Pinned by |
|---|---|---|---|
| 1 | `unpublish` **frees the slug**; `republish` **reassigns** it — the URL can come back different | **Silently, in public.** Links and bookmarks break, and nothing in the response says the slug moved | `test_unpublish_republish_can_change_the_slug` + descriptions |
| 2 | `delete_published_course` is a **soft unpublish**, near-identical to `unpublish_published_course` | Two tools, one behaviour; a model picks arbitrarily | `test_delete_and_unpublish_descriptions_disambiguate` |
| 3 | `slug`, `course` and `domain` are **create-only**; update silently ignores them | **Silently.** ADR-008 says reject what upstream ignores | `test_update_rejects_create_only_fields` |
| 4 | `require_all_prerequisites` and `unique_progress_per_enrollment` default **TRUE**; every other boolean defaults false | Silently, in the opposite direction from the guess | `test_the_two_true_defaults_are_documented` |
| 5 | `VisibilityOverrideAttributes` uses `updated_at`, not `modified_at` | Silently — the field vanishes | `test_visibility_overrides_expose_updated_at` |
| 6 | `(group, course, is_visible=true)` and `(…, false)` **can coexist** — the unique key includes `is_visible` | Silently. Contradictory rows, and upstream says clients should pick one | `test_allow_and_block_rows_can_coexist` + description |
| 7 | `remove_visibility_overrides` echoes the **published_course_id** in `BatchDeletedItem.id`, not the override's own id | Silently mis-correlates results | `test_remove_echoes_the_published_course_id` |
| 8 | Publishing the same course to the same domain twice is a **per-item** `already_published`, not a batch failure | A caller aborts a batch that mostly succeeded | `test_duplicate_publish_is_a_per_item_conflict` |
| 9 | `list_visibility_overrides` 404s at the **document** level for a missing group, distinct from a per-item not_found inside a 207 | Confuses "no such group" with "no overrides" | `test_missing_group_is_a_document_level_404` |

---

## Files

- Create: `src/csa_skilljar/mcp/_tools/publishing.py` (9 tools), `.../catalog.py` (2 domain tools)
- Modify: `.../_tools/groups.py` — the 3 visibility-override tools live with the group family
- Create: `tests/test_publishing.py`, `tests/test_catalog.py`; extend `tests/test_groups.py`
- Modify: `backend.py` (12 methods × 3 layers), `client.py`, `_schemas.py`, `policy.py`,
  `server.py`, `_tools/__init__.py`
- Modify: `tests/test_protocol.py`, `test_policy.py`, `test_descriptions.py`
- Modify: `README.md` (→ 70 tools), `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`

## Capabilities

- `publishing.read` — `list_published_courses`, `get_published_course`, `list_domains`,
  `get_domain`. In `parity` and `operations`.
- `publishing.write` — `publish_courses`, `update_published_courses`,
  `delete_published_course`, `unpublish_published_course`, `republish_published_course`.
  **In no profile but `full`**, because these are the public-facing ones.
- `groups.read` / `groups.write` — the three visibility-override tools, per the scope routing
  above.

## Task sequence

- [ ] **Task 1 — Domains.** `list_domains`, `get_domain`. Smallest family; establishes
      `publishing.read` and the `include` parameter.
- [ ] **Task 2 — Published-course reads.** `list_published_courses`, `get_published_course`.
- [ ] **Task 3 — Publish and update.** `publish_courses`, `update_published_courses`.
      Traps 3, 4, 8.
- [ ] **Task 4 — Lifecycle.** `delete_published_course`, `unpublish_published_course`,
      `republish_published_course`. Traps 1 and 2.
- [ ] **Task 5 — Visibility overrides.** All three, into `groups.py`. Traps 5, 6, 7, 9.
- [ ] **Task 6 — Mutations, docs, PR.**

## Mutations required before the PR

| Mutation | Must be killed by |
|---|---|
| `update_published_courses` accepts `slug` | `test_update_rejects_create_only_fields` |
| `publishing.write` folded into `content.write` | policy matrix + `test_authoring_cannot_publish` |
| `_OVERRIDE_KEYS` says `modified_at` | `test_visibility_overrides_expose_updated_at` |
| `remove_visibility_overrides` echoes the override id | `test_remove_echoes_the_published_course_id` |
| Duplicate publish fails the whole batch | `test_duplicate_publish_is_a_per_item_conflict` |

**Ships:** v0.7.0 — still queued behind `WAITING-FOR-002`.
