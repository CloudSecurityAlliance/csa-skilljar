# Block 6 — Students — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Eight tools over learner records — including irreversible PII erasure and an account-takeover primitive.

**Architecture:** Reads and the batch writes follow the established shape. Four tools do not, and they are the reason this block is scheduled sixth rather than second.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · [`SECURITY-RESOURCES.md`](../../../SECURITY-RESOURCES.md) · Contracts: [`specs/official-mcp/`](../../../specs/official-mcp/)

## Global Constraints

Unchanged from Blocks 2–5.

---

## Why this block is here and not earlier

The roadmap put students sixth on purpose: *"deliberately placed after the gating machinery has been exercised three times."* It has now been exercised five times, and mutation-tested in every one.

Four of these tools are the ones `SECURITY-RESOURCES.md` names as the reason capability gating exists:

| Tool | What it does that cannot be undone |
|---|---|
| `anonymize_student` | permanently erases a real person's PII |
| `set_student_password` | account takeover — sets a password directly |
| `send_password_reset` | emails a real person a reset link |
| `deactivate_student` | removes a learner's access |

Every one is reachable by an agent that read a lesson body. That is the confused-deputy scenario, and this block is where it stops being hypothetical.

---

## What is new

### 1. A capability tier below `people.write`

`DESTRUCTIVE_PEOPLE` already exists in `policy.py` and is used by nothing. It gates all four of the above. `people.write` covers only `create_students` and `update_students`.

**No profile except `full` grants `people.destructive`.** `people` grants read + write, so a credential for routine learner administration cannot erase anyone.

### 2. `X-Confirm-Destructive: true` — an API-level gate independent of OAuth

From the captured registry, on `anonymize_student`:

> Requires the `X-Confirm-Destructive: true` HTTP header. An API-level confirmation gate distinct from OAuth scope — reproduce it, and surface a clear error when absent rather than a bare 4xx.

Nothing in the codebase sends custom headers yet. `_send` needs a `headers` parameter, and `V2Backend.anonymize_student` must set it. **Do not send it on any other call** — the whole point is that it is specific to the irreversible operation.

The tool also takes its own `confirm: bool` parameter, defaulting to `False`, refused when unset. Two independent confirmations: one the caller must pass, one the wire must carry.

### 3. `update_students` has a dual identifier, and `email` is read-only

- `id` **or** `attributes.email` identifies the row; at least one is required.
- With `id` absent, `email` identifies and **cannot also be changed**.
- With `id` present, `email` is a **confirmation** — a mismatch is a per-item `validation_error`.
- `email` is never writable either way.

That third case is a genuine safety feature and worth exposing: passing both is how a caller says *"update this id, and fail if it is not who I think it is."*

### 4. The two-PATCH rule

> To reactivate AND modify other fields you must send TWO separate PATCHes: first `{is_inactive: false}`, then the other fields. A single combined PATCH does not work.

The API accepts a combined call and silently does not apply the other fields. Reject it locally with a message saying to split it — same reasoning as ADR-008.

### 5. `send_password_reset` requires `domain`

The reset link is domain-scoped, so there is no sensible default. A missing domain must be a local error naming `list_domains` as the way to find one.

---

## Tasks

- [ ] **Task 1 — reads and batch writes.** `list_students` (`filter_email` exact/case-insensitive, `filter_first_name`, `filter_last_name`, `filter_is_inactive`, paginated), `get_student`, `create_students` (first-wins dedup on email), `update_students` (dual identifier, read-only email, two-PATCH rule).

- [ ] **Task 2 — `_send` gains headers, and `anonymize_student`.** Add `headers:` to `_send`; assert in a `V2Backend` test that the header is present on anonymize and **absent everywhere else**. The tool requires `confirm=True`.

- [ ] **Task 3 — the other three destructive tools.** `deactivate_student`, `set_student_password`, `send_password_reset`. All gated on `people.destructive`; `set_student_password` also requires `confirm=True`.

- [ ] **Task 4 — gates, integration, docs.** Extend the hand-written matrix for `people.read`, `people.write`, `people.destructive`; assert `people` grants read+write and **not** destructive. Read-only live assertions. Re-review `SECURITY-RESOURCES.md`, which the Block 1 plan said must happen when this block lands.

---

## Self-Review

**The trap I expect.** Sending `X-Confirm-Destructive` on every request because it is easier than threading it through one call. That silently removes the API's own safety gate for any future destructive endpoint. The test must assert the header is absent on a normal call.

**Second trap.** Letting `confirm` default to `True`, or accepting a truthy string. It defaults to `False` and only `True` proceeds.

**A judgement call I am making.** These tools ship present-and-off rather than not at all, per `SECURITY-RESOURCES.md`: *"having a tool and being permitted to call it are separate facts."* A default install cannot call any of them.
