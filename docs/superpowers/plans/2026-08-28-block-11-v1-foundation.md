# Block 11 — v1 foundation + learner progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** `V1Backend` — the second API — and the first v1-only capability: a learner's
per-course progress.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · ADR-002 (routing) ·
ADR-007 (family order) · v1 OpenAPI `specs/skilljar-v1-openapi.json`

## Global Constraints

Unchanged from Blocks 2–10. Plus ADR-002, which this block is the first real test of:
**v2 owns every capability v2 has; v1 is used only for capabilities v2 lacks. No fallback,
no dual-routing.**

---

## The roadmap's premise did not survive probing

Block 11 was specified as *"per-lesson learner progress"*, done when *"per-lesson progress
is readable for a learner in a course"*.

**That endpoint does not exist on the live API.** `GET /v1/users/{user_id}/published-courses/{published_course_id}/lessons`
is in Skilljar's published v1 OpenAPI document and returns **404**.

Probed 2026-08-28 with the read-only v1 key, walking the prefix one segment at a time:

```
200  /v1/users/<uid>
200  /v1/users/<uid>/published-courses
200  /v1/users/<uid>/published-courses/<pcid>
404  /v1/users/<uid>/published-courses/<pcid>/lessons
```

With controls, because the probe means nothing without them:

```
401  /v1/users              no auth          (auth is enforced)
200  /v1/users              with auth        (the key works)
404  /v1/totally-made-up    with auth        (404 = no such endpoint)
```

The parent resolves, only the sub-resource 404s, and the key is not the problem. Every
other route to per-lesson progress was tried and also 404s: `/v1/course-progress/{id}/lessons`,
`/v1/enrollments/{id}/lessons`, `/v1/lesson-progress?course_progress_id=`,
`/v1/published-courses/{id}/lessons`. `/v1/progresstokens` returns **200 with zero rows**,
which matches ADR-007's finding that progresstokens is one of four empty families.

**So the published v1 spec documents an endpoint this deployment does not serve.** This is
the mirror of the v2 finding already recorded in `CLAUDE.md` — there the metadata runs
ahead of the API, here it runs ahead too, just in a document old enough that nobody
noticed.

## What the block becomes

The foundation half is unchanged and is what Blocks 12–17 need. The capability half moves
from per-lesson to **per-course** progress, which is real, populated, and genuinely absent
from v2.

`GET /v1/users/{uid}/published-courses[/{pcid}]` returns, per enrolment:

| Field | In v2? |
|---|---|
| `course_progress.completed_lesson_count` | **no** |
| `course_progress.completed_required_lesson_count` | **no** |
| `course.lesson_count` / `required_lesson_count` | **no** |
| `course_progress.credits_earned` / `credit_unit_plural` | **no** |
| `course_progress.latest_activity` | **no** |
| `all_enrollments[]` — re-enrolment history | **no** |
| score, max_score, success_status, completed_at | yes (v2 `list_enrollments`) |

v2's `EnrollmentAttributes` carries no lesson counts, no credits, no re-enrolment history.
"How far through is this learner, in lessons" is a question **only v1 can answer**, which
is exactly the ADR-002 test: v1 earns a tool because v2 lacks the capability, not because
it also has it.

## The traps

| # | Trap | Fails how | Pinned by |
|---|---|---|---|
| 1 | v1 has **two envelope shapes** — DRF `{count,next,previous,results}` AND bare JSON arrays | Silently: a uniform reader returns nothing for half the endpoints | `test_both_v1_envelope_shapes_are_read` |
| 2 | v1 pagination is `?page=N` with a **total count** — not v2's opaque cursor | A cursor-shaped reader cannot page v1 at all | `test_v1_paginates_by_page_number_not_cursor` |
| 3 | v1 auth is **HTTP Basic, API key as username, empty password** | 401 that looks like a bad key | `test_v1_sends_basic_auth_with_an_empty_password` |
| 4 | The listing row **nests** the learner under `user` | A reader looking for `id` at the top finds nothing | `test_the_v1_user_row_nests_the_learner` |
| 5 | v1 and v2 learner ids are **the same id space** — observed, not documented | A translation layer nobody needs, or a wrong assumption they differ | `test_v1_and_v2_learner_ids_are_the_same_space` (integration) |
| 6 | Per-lesson progress **does not exist** | A tool built against the spec would 404 forever | `test_no_tool_claims_per_lesson_progress` |

## Files

- Create: `src/csa_skilljar/v1backend.py`, `src/csa_skilljar/mcp/_tools/progress.py`
- Create: `tests/test_v1backend.py`, `tests/test_progress.py`
- Modify: `backend.py` (the `Backend` Protocol gains the v1 methods), `client.py`,
  `_schemas.py`, `policy.py`, `server.py`, `_tools/__init__.py`, `_config.py`
- Modify: the coverage tables — `test_protocol.py`, `test_policy.py`,
  `test_descriptions.py`, `test_pagination.py`, `test_parity.py`
- Modify: `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`, `WAITING-FOR-001.md`

## Capability

`progress.read`, in `parity` and `operations`. A read of learner progress is no more
sensitive than `list_enrollments`, which `parity` already grants.

## Task sequence

- [ ] **Task 1 — `V1Backend`.** HTTP Basic, both envelope shapes, page-number pagination,
      v1 error translation into the same typed exceptions v2 raises.
- [ ] **Task 2 — `FakeV1Backend`** with both shapes, so the double cannot teach a lesson
      the real API does not.
- [ ] **Task 3 — the tools.** `list_learner_progress`, `get_learner_progress`.
- [ ] **Task 4 — routing.** Assert no capability is served by both backends (ADR-002).
- [ ] **Task 5 — record the missing endpoint**, mutations, docs, PR.

**Ships:** v0.10.0.
