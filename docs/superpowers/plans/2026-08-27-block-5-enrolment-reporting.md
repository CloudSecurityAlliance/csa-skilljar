# Block 5 — Enrolment & Reporting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Nine tools covering who is enrolled, how they are doing, and what they earned — plus the first operations in this project that **send email to real people**.

**Architecture:** Reads follow the established pattern. The three writes do not: one has a hybrid envelope, one forces the caller to decide about notifications, and one treats `null` as invalid where its siblings treat it as "clear".

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · Contracts: [`specs/official-mcp/`](../../../specs/official-mcp/) · Established pattern: [Block 2 plan](2026-08-26-block-2-courses-and-lessons.md)

## Global Constraints

Unchanged from Blocks 2–4.

---

## What is new

### 1. These tools affect real people, not content

Everything before this block edited course material. `bulk_enroll_students` puts named humans into a course, and `complete_enrollments` can email them saying they passed. Two consequences:

- Both are gated on `WRITE_ENROLMENT`, which is in `operations` and `full` but **not** in `authoring`.
- Both descriptions must state the outward-facing effect plainly, and say to act only on the user's explicit instruction. A model that bulk-enrols 400 people because a lesson body suggested it is the confused-deputy scenario `SECURITY-RESOURCES.md` names.

### 2. `bulk_enroll_students` has a HYBRID envelope

Not a plain batch. `published_course_id` and `expires_at` are shared at the **top level**; `data` carries per-row `{email}` items. Reproduce the shape exactly.

- `expires_at` must be in the **future** — a past value is a request-level `400`, not a per-item failure. Check locally.
- First-wins duplicate detection on `email`; later occurrences are pre-marked `duplicate_in_batch` without reaching the service.
- Emails are normalised to lowercase server-side.

The per-row failure vocabulary lives in a Skilljar document that is **not public**, so it has to be learned empirically. Do not invent codes; pass through whatever comes back.

### 3. `send_notifications` is REQUIRED, not defaulted

On `complete_enrollments`. From the captured registry: *"the caller is forced to decide whether learners get email. Preserve that; defaulting it silently mails people."*

So it is a required parameter with **no default**, and the description says what each value does.

### 4. `null` means three different things across two tools

| Field | `null` means |
|---|---|
| `update_enrollments.active` | **INVALID.** Omit to leave unchanged. |
| `update_enrollments.due_at` / `expires_at` | clear the value |
| `complete_enrollments.completed_at` | **remove the completion** |
| `complete_enrollments.success_status` | clear passed/failed |

`active: null` must be rejected locally with a message saying to omit it instead.

### 5. Two reporting tools are course-scoped and unpaginated

`get_course_analytics` and `list_course_ratings` both require `course_id`. Ratings are not paginated and come back most-recent-first. Do not add pagination.

### 6. Ratings and analytics carry learner-written text

`list_course_ratings` returns student feedback. That is untrusted, attacker-influencable content and the description must say so — it is the same confused-deputy surface as lesson HTML.

---

## Tasks

- [ ] **Task 1 — enrolment reads.** `list_enrollments` (filters: `active`, `completed_gte/lte`, `enrolled_gte/lte`, `course.id`, `domains`, `progress_status`, `student.email`, `student.id`, `include`; genuinely paginated upstream), `get_enrollment` (with `include`).

- [ ] **Task 2 — certificates and analytics.** `list_certificates` (`status` enum defaults to `all`), `get_certificate`, `get_course_analytics`, `list_course_ratings` (unpaginated, untrusted text).

- [ ] **Task 3 — enrolment writes.** `update_enrollments` (reject `active: null`), `complete_enrollments` (required `send_notifications`), `bulk_enroll_students` (hybrid envelope, future-dated `expires_at`).

- [ ] **Task 4 — gates, integration, docs.** Extend the hand-written matrix for `reporting.read` and `enrolment.write`; assert `authoring` grants neither. Read-only live assertions. README, CHANGELOG, ROADMAP, TODO.

---

## Self-Review

**The trap I expect.** Giving `send_notifications` a default. It reads as a convenience and it silently emails learners. The test must assert calling without it is an error.

**Second trap.** Treating `active: null` like `due_at: null`. They are adjacent fields on the same tool with opposite meanings.
