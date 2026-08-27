# Block 4 — Question Banks & Bindings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Ship the highest-value block for CSA — reusable exam item pools, and the quiz↔bank binding that makes them reusable.

**Architecture:** Banks follow the established CRUD shape exactly. The four **binding** tools do not: they operate on a join row identified by a natural key rather than an id, and their update semantics differ from every other write in the project.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · Contracts: [`specs/official-mcp/`](../../../specs/official-mcp/) · Established pattern: [Block 2 plan](2026-08-26-block-2-courses-and-lessons.md)

## Global Constraints

Unchanged from Blocks 2–3.

---

## Why this block matters

A published claim said question banks were v1-only. They are not — v2 has full CRUD **and** the binding, while v1 cannot add a question to a bank or bind a bank to a quiz at all. This block is where reusable TAISE-style exam content becomes programmatically manageable, and it is the single strongest argument for this project existing.

---

## What is new

### 1. Re-binding is an idempotent PARTIAL update — the critical semantic

Verbatim from the captured registry:

> Re-binding an already-bound bank is an IDEMPOTENT PARTIAL UPDATE. Only fields the caller actually supplies are written; any writable field **OMITTED on re-bind is PRESERVED** at its stored value — **NOT** reset to a schema default, and an omitted `order` is **NOT** re-derived.

So `bind_quiz_question_banks` with `{question_bank_id: "b1"}` against an already-bound bank changes **nothing**. It does not reset `order`, does not reset `randomize_questions`, does not move the bank to the end. Implemented upstream as `update_or_create` on the natural key, so it never raises an integrity error.

This is the opposite of what "bind" suggests, and getting it wrong silently reorders someone's exam.

### 2. Two different dedup rules in one block

`bind_quiz_question_banks` and `update_quiz_question_banks` are **first-wins** on `question_bank_id`, so a logical bind fires its event exactly once. Most updates elsewhere are last-write-wins. Do not generalise.

### 3. `unbind` is a HARD delete

`QuestionBankAssignment` is not a soft-deletion model — the rows are permanently removed. The bank and its questions are untouched; only the link goes.

### 4. `list_quiz_question_bank_assignments` is not paginated, on purpose

It returns a plain `{"data": [...]}` envelope, because a quiz's bank assignments are a small bounded set. **Do not add `page_cursor`/`page_size`** — additive compatibility means adding what is *missing*, not imposing a shape the resource does not have. A malformed or cross-org `quiz_id` is a document-level 404, not a per-item error.

### 5. `question_bank_id` lives under `attributes`, not as a top-level `id`

Even for unbind. That keeps it symmetric with bind and update, and makes the per-item JSON:API pointer resolve to `/data/{i}/attributes/question_bank_id`. Reproduce the shape.

### 6. An empty attributes set is a NO-OP SUCCESS

`update_quiz_question_banks` with only `question_bank_id` and nothing to change succeeds and changes nothing. Do not reject it as "no fields supplied".

### 7. Deleting a bank leaves quizzes alive

Cascade: soft-deletes the bank's questions and their answers, **hard**-removes every assignment referencing the bank (unbinding any quizzes that used it), then soft-deletes the bank. **Quizzes that referenced it stay alive** — only their assignment rows go. This belongs in the description: a model deleting a bank must know it will silently unbind live exams.

---

## Tasks

- [ ] **Task 1 — bank CRUD.** `list_question_banks` (`filter_name` exact, `filter_updated_since`, plus additive pagination), `get_question_bank`, `create_question_banks`, `update_question_banks` (`name` is the ONLY writable field), `delete_question_banks` gated on `content.delete` with the cascade documented.

- [ ] **Task 2 — the binding tools.** `list_quiz_question_bank_assignments` (unpaginated), `bind_quiz_question_banks`, `unbind_quiz_question_banks`, `update_quiz_question_banks`. All four take `quiz_id` as a path resource. Bind/update/unbind are batch over `data`; the natural key is `attributes.question_bank_id`.

- [ ] **Task 3 — prove the partial-update semantic.** A test that binds with `order` and `randomize_questions`, re-binds supplying only `question_bank_id`, and asserts **both stored values survive**. This is the behaviour most likely to be implemented wrongly and the one that quietly corrupts an exam.

- [ ] **Task 4 — integration, docs.** Read-only live assertions for banks and assignments. README, CHANGELOG, ROADMAP, TODO.

---

## Self-Review

**The trap I expect.** Implementing `bind` as create-or-replace rather than create-or-*merge*. It passes a naive test (bind twice, one row exists) and silently resets `order` and `randomize_questions` on every re-bind. Task 3 exists specifically to catch it, and it must be written before the implementation.

**Not repeated here:** the batch envelope, `_batch_out`, `_check_write_items`, gating, and the fake/real seam are established and unchanged.
