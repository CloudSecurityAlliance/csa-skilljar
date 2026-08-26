# Roadmap

Sequence, not dates. `GOALS.md` says what success is; this says in what order we get there.

Work is organised into **blocks**. A block is one coherent slice of capability, small enough to
hold in one head, that ships on its own. Blocks run one at a time, in order, each through the same
loop — and a block is not done until it is released.

**Confidence:** Committed (in flight) · Planned (agreed, not started) · Exploratory (outcome TBD) ·
Deferred (not now, trigger noted)

---

## The block loop

Every block runs the same seven steps. The discipline is that step 7 is a real gate: no block
starts before the previous one has shipped.

```
  1. PLAN       write docs/superpowers/plans/NN-<block>.md via the writing-plans skill
                → bite-sized TDD steps, each independently reviewable
  2. SPEC?      only if the block changes the design. Otherwise skip — do not
                re-derive settled decisions. A change here means a new ADR.
  3. RED        write the failing tests first, against FakeBackend
  4. GREEN      implement until they pass
  5. VERIFY     the block's definition of done, below — run it, do not assume it
  6. SHIP       version bump + CHANGELOG + tag → PyPI via Trusted Publishing
  7. LOOP       next block
```

**Every block inherits the same definition of done**, on top of its own:

- offline unit tests pass with no network and no credentials
- `ruff` + `mypy` clean; coverage floor holds
- every new `Backend` method has a declared gate in `_GATES` (fails closed)
- every new tool has a description stating what it returns, what it does **not** return, and which
  argument is required and why
- no tool name matches `^v[0-9]_` or contains `_v1_` / `_v2_` (ADR-004)
- nothing on the block's code paths writes to stdout
- `CHANGELOG.md` entry, and `README.md` status banner still honest

---

## Now

### Block 0 — Foundation · Committed

The walking skeleton. No user-facing capability except the two meta tools; everything after this
is filling in a shape that already works end to end.

Packaging (`pyproject.toml`, `src/` layout, typed marker, single-sourced version) · `Backend`
protocol · `V2Backend` · `FakeBackend` · conformance test across implementations ·
`PolicyBackend` with fail-closed `_GATES` · profiles · `client_credentials` auth (ADR-003) · the
seven-state auth error taxonomy · local scope pre-check from the spec · two-tier startup checks ·
`ToolError` translation decorator · CI (lint, type-check, matrix, coverage, security) · branch
protection · `SECURITY.md` + `RELEASING.md`.

Ships two tools: **`check_access`**, **`describe_capabilities`** — plus **`list_courses`** as the
single vertical slice that proves the whole stack.

**Done when:** `list_courses` returns real data through the MCP protocol against live Skilljar;
all seven auth states produce distinct messages, tested; the stdout test exists and passes; a
hand-written capability expectation matrix exists (never derived from the gate table); branch
protection is on with required checks.
**Blocked by:** `WAITING-FOR-002` — a v2 client credential.
**Ships:** v0.1.0

---

## Next — completing parity (73 tools)

Blocks 1–8 implement the official Skilljar MCP server's tool surface, with additive compatibility
(ADR-006). Order is value-first, with the destructive tools deliberately late so the gating
machinery is proven before it matters.

### Block 1 — Courses & lessons · Planned · 8 tools

`list_courses` `get_course` `create_courses` `update_courses`
`list_lessons` `get_lesson` `create_lessons` `update_lessons`

Establishes the CRUD pattern every later block copies, and the batch-write envelope (v2 collection
writes return `207` with per-item results).

**Done when:** a course with lessons can be created, read back and updated; batch partial failure
is surfaced per item, not collapsed into one error.
**Ships:** v0.2.0

### Block 2 — Quizzes & questions · Planned · 10 tools

`list_quizzes` `get_quiz` `create_quizzes` `update_quizzes` `delete_quizzes`
`list_questions` `get_question` `create_questions` `update_questions` `delete_questions`

First block with `delete_*`, so the first real exercise of capability gating.

**Done when:** a quiz with questions round-trips; deletes are refused under the default profile and
permitted under an explicit one, proven by the one-capability-at-a-time matrix.
**Ships:** v0.3.0

### Block 3 — Question banks & bindings · Planned · 9 tools

`list_question_banks` `get_question_bank` `create_question_banks` `update_question_banks`
`delete_question_banks` `bind_quiz_question_banks` `unbind_quiz_question_banks`
`update_quiz_question_banks` `list_quiz_question_bank_assignments`

**The highest-value block for CSA.** Reusable exam item pools across certifications — and the
capability a widely-repeated published claim said did not exist in v2 (`FRICTION-002`).

**Done when:** a bank can be created, populated, bound to a quiz with a weighting, rebound and
unbound — the full TAISE item-reuse pattern, executed end to end.
**Ships:** v0.4.0

### Block 4 — Enrolment & reporting · Planned · 9 tools

`list_enrollments` `get_enrollment` `update_enrollments` `complete_enrollments`
`bulk_enroll_students` `list_certificates` `get_certificate` `get_course_analytics`
`list_course_ratings`

Read-heavy and high value. Note this is *course-level* progress only — per-lesson is v1 and
arrives in Block 10.

**Done when:** enrolment state and scores are readable for a real course; bulk enrolment reports
per-item results; the description says plainly that per-lesson detail is not available here.
**Ships:** v0.5.0

### Block 5 — Students · Planned · 8 tools

`list_students` `get_student` `create_students` `update_students` `anonymize_student`
`deactivate_student` `set_password` `send_password_reset`

**The dangerous block.** Irreversible PII erasure and an account-takeover primitive. Deliberately
placed after the gating machinery has been exercised three times.

**Done when:** all four sensitive tools are present and **off** under the default profile; each is
individually enablable; the scope pre-check produces the exact-missing-scope message without a
network call; `SECURITY-RESOURCES.md` is re-reviewed.
**Ships:** v0.6.0

### Block 6 — Groups & signup fields · Planned · 11 tools

`list_groups` `get_group` `create_groups` `update_groups` `delete_groups`
`add_group_memberships` `remove_group_memberships`
`list_signup_field_values` `get_signup_field_value` `create_signup_field_values`
`update_signup_field_values`

Watch for `GroupAttributes.updated_at` — every other v2 object uses `modified_at`. A uniform
assumption breaks group sync silently.

**Done when:** membership add/remove works; the timestamp inconsistency is handled and has a
regression test naming it.
**Ships:** v0.7.0

### Block 7 — Publishing & catalog · Planned · 12 tools

`list_published_courses` `get_published_course` `publish_courses` `update_published_courses`
`delete_published_course` `unpublish_published_course` `republish_published_course`
`add_visibility_overrides` `remove_visibility_overrides` `list_visibility_overrides`
`list_domains` `get_domain`

Note the inversion: v1 hangs visibility off the content object, v2 hangs it off the group.

**Done when:** a course publishes to a domain, becomes visible to a group, and unpublishes.
**Ships:** v0.8.0

### Block 8 — Web packages & OAuth client · Planned · 6 tools

`list_web_packages` `get_web_package` `create_web_packages` `update_web_packages`
`delete_web_package` · `register_oauth_client`

Small closing block. `register_oauth_client` mints a credential, so it goes behind the `admin`
profile even though the official server ships it on.

**Done when:** the registry diff against the live official server shows **zero missing tools** —
parity is a passing test, not a claim (ADR-006).
**Ships:** v0.9.0 — **parity complete**

---

## Later — beyond parity

### Block 9 — Remaining v2: credential administration · Planned · 8 tools

`GET /v2/scopes/` and the six `/v2/clients/` operations, plus `auth/revoke`. Everything the
official server omits.

Skilljar exposes the tool that *mints* a credential and withholds the ones that *audit and
remediate* — this block restores the second half. All of it sits behind `admin`, off by default.

**Ships:** v0.10.0

### Block 10 — v1 foundation + learner progress · Planned

`V1Backend` (HTTP Basic, DRF envelope, cursor pagination with a total count), v1 error
translation, and the first v1 family: per-lesson learner progress.

The **largest functional gap in v2**, and first by evidence (ADR-007). Note `GET /v1/lessons`
requires `course_id` — enumerating lessons org-wide is impossible on v1, and the description must
say so.

**Done when:** per-lesson progress is readable for a learner in a course, through a tool whose
name carries no version marker; the two backends coexist with no fallback path (ADR-002).
**Ships:** v0.11.0

### Blocks 11–16 — the remaining v1 families · Planned

Ordered by usage evidence in the reference org, not by API size.

| # | Block | Why here |
|---|---|---|
| 11 | Assets & media | 157 assets, 533 web packages. v2 has **no file upload at all** |
| 12 | Commerce (read-biased) | 13,687 promo codes, 4,278 pools — the volume leader. Reads yes, bulk creation no |
| 13 | Learning paths | 10 published paths, 14 course series |
| 14 | Events & webhooks | Only 3 subscribed, but the cleanest compression: 10 `sample-*` endpoints → one `preview_event_payload(event_type)` |
| 15 | vILT / ILT | 341 registrations; ILT proper is thin (9 instructors) |
| 16 | Labels & tags | Small, self-contained, finishes the set |

**Ships:** v1.0.0 on completion of Block 16 — the point at which every capability CSA's org
actually uses is reachable.

---

## Aspirational

- **The demonstration that is also the end-to-end test.** Worth building once there are enough
  tools for a tour to be worth taking — probably after Block 4. Returns the *plan*, not the
  result, so the model calls the tools and the tool descriptions get tested.
- **Shrinking.** Each v1 family retired as v2 ships its equivalent, triggered by
  `check_upstream.py` and `WAITING-FOR-001`. **A block that deletes code is a success.**
- **Answering the five research questions** in design spec §10, contributed back to
  CINO-Platform-Engineering as the third-server data point.

---

## Parked

| Item | Why | Revisit trigger |
|---|---|---|
| Catalog page-building (~60 v1 ops) | An agent should not drive a page builder | A concrete CSA need |
| License packages, progress tokens, multi-session events, access-code pools | **Zero rows** in the reference org (ADR-007) | Any non-zero count from `check_upstream.py` |
| Webhook *receiving* | We manage subscriptions; being an HTTP endpoint is a different product | — |
| Caching | Sessions are live and multi-actor | Would need its own ADR and a security re-review |
| Cross-API composite writes | v2 has batch with per-item results; v1 has nothing equivalent | — |
| `PlaywrightBackend` for API-impossible operations | None identified yet | A capability that exists in the UI and neither API |

---

## Honest uncertainty

- **Block 0 is blocked** on a v2 client credential (`WAITING-FOR-002`). Nothing else can start.
- **Blocks 10–16 may shrink or vanish** before they are built. That is the design working, not a
  plan failing — check `WAITING-FOR-001` before starting any of them.
- **No dates.** This is one engineer working through AI, part-time. The order is committed; the
  pace is not.
- **Blocks 11–16 are demand-driven.** Each is independently shippable, so the project can stop at
  any block boundary without leaving anything half-built.
