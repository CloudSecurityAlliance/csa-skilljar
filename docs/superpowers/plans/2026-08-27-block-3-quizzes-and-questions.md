# Block 3 — Quizzes & Questions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship v0.2.0 — ten tools over quizzes and questions, and the project's first destructive operations.

**Architecture:** Structurally identical to Block 2 — `Backend` methods, `_GATES` entries, batch writes through `parse_batch`. This plan documents only what is **new**; for the established CRUD and batch pattern read [the Block 2 plan](2026-08-26-block-2-courses-and-lessons.md), which is not repeated here.

**Tech Stack:** unchanged from Block 2.

**Spec:** [design spec](../specs/2026-08-26-csa-skilljar-design.md) · Contracts: [`specs/official-mcp/`](../../../specs/official-mcp/)

## Global Constraints

All of Block 2's apply unchanged: venv-only commands, `./scripts/verify.sh` before every commit (enforced by `.githooks/pre-commit`), no suppressed output, `ToolError` at the boundary, `TypedDict` from `typing_extensions`, no version marker in a tool name, additive compatibility (ADR-006), a `_GATES` entry for every `Backend` method, and every guard mutation-tested once.

---

## What is new in this block

### 1. The first destructive operations, and a capability for them

`delete_quizzes` and `delete_questions` are the project's first deletes. They must **not** be gated on `content.write`: an authoring credential that can create and update should not thereby be able to destroy. Add a new capability.

```python
DELETE_CONTENT = "content.delete"
```

Profiles: `authoring` gets `content.read` + `content.write` and **not** delete. `full` gets everything. No default profile grants delete.

### 2. Cascade semantics belong in the descriptions

Verbatim from the captured registry, and not in the OpenAPI document:

- **`delete_quizzes`** — soft-deletes the quiz's **own** questions and their answers; **hard**-removes its question-bank assignments; then soft-deletes the quiz. **Shared question banks and their questions are untouched** — a quiz only owns questions where `question.quiz == quiz`.
- **`delete_questions`** — soft-deletes the question's answers, then the question. The parent quiz or bank and its other questions are untouched.

A model deleting a quiz must be able to learn, from the description alone, that shared banks survive. Both descriptions state it.

### 3. The question XOR, and why the scope is OR

A question is homed under a quiz **XOR** a question bank. Both → error. Neither → error. That is exactly why the scope is `question-banks:* OR quizzes:*`.

### 4. Cross-state validation is per-item, not schema-level

A flag conflicting with the **stored** `question_type` — `case_sensitive` on a stored `MULTIPLE_CHOICE` — is a **per-item `validation_error` inside a 207**, not a document-level 422. The schema cannot see the stored type.

**This is the first validation we cannot do locally**, and the distinction matters: local checks reject the whole call, this one fails one row. Do not try to pre-check it.

### 5. Fields the API rejects on create

`order`, per-answer `order`, `is_graded`, `is_optional` and `answer_feedback_html` are **not accepted** on `create_questions` — the service assigns order (`idx*10` by array position) and the rest take model defaults. `extra=forbid` upstream makes an attempt a 422 rather than a silent drop, so reject locally with a message naming the reason.

### 6. Two quirks to encode

- **`answers` are IMMUTABLE on update.** There is no `answers` field on `update_questions`. To change them, delete and recreate the question. The description must say so, or a model will silently fail to change an exam.
- **`FILL_IN_THE_BLANK` forces `correct=True`** on every answer regardless of what was sent. Accepted for a uniform wire shape, then overridden. Say so rather than letting a caller believe their `correct: false` took effect.

### 7. Answer shape

`answers` is required and non-empty for `MULTIPLE_CHOICE`, `MULTIPLE_ANSWER` and `FILL_IN_THE_BLANK`, and **must be empty** for `FREEFORM`. Each answer: `answer_text` (required, max 1000) and `correct` (default false). `CONTENT_UPLOAD` and `LINEAR_SCALE` exist in Skilljar's model but are rejected — the enabled set is four.

---

## Tasks

Each follows Block 2's rhythm: write the failing test, run it, implement, run it, verify, commit.

- [ ] **Task 1 — `content.delete` capability.** Add `DELETE_CONTENT`, put it in `full` only, extend the hand-written matrix in `tests/test_policy.py`. Mutation-test by gating a delete on `WRITE_CONTENT` and confirming the matrix fails.

- [ ] **Task 2 — quiz reads.** `list_quizzes` (`filter_name` exact/case-insensitive, `filter_updated_since`, plus our `page_cursor`/`page_size`), `get_quiz`. Backend, gates, client, schemas `QuizOut`/`QuizListOut`/`QuizDetailOut`, tools, and entries in the protocol `EXERCISE` and description `REQUIREMENTS` tables.

- [ ] **Task 3 — quiz writes.** `create_quizzes`, `update_quizzes`. Attributes and their defaults are listed in `specs/official-mcp/registry-create-tools.json` and `registry-update-tools.json`; reproduce them exactly, reject unknown attributes, and validate `passing_percentage_correct` 0..100 and `time_limit_seconds` 0..3600000 locally.

- [ ] **Task 4 — question reads.** `list_questions` (`filter_quiz_id`, `filter_question_bank_id`), `get_question` (answers nested inline).

- [ ] **Task 5 — question writes.** `create_questions` with the XOR, the answer-shape rules, the four enabled types, and local rejection of the not-accepted fields. `update_questions` **without** `answers`, rejecting `question_type`, `quiz_id`, `question_bank_id` and `order` as read-only per ADR-008.

- [ ] **Task 6 — deletes.** `delete_quizzes`, `delete_questions`. Batch, gated on `content.delete`, `DESTRUCTIVE` annotation, cascade documented in each description. Test that both are refused under `authoring` and permitted under `full`.

- [ ] **Task 7 — integration, docs, release.** Extend `tests/integration/` with read-only quiz and question assertions. Update README tool table, CHANGELOG, ROADMAP, TODO. Bump to `0.2.0` and release once `WAITING-FOR-002` clears.

---

## Self-Review

**Coverage.** Every tool in the roadmap's Block 3 list has a task. The new capability has its own task ahead of the tools that need it, avoiding Block 2's ordering wrinkle where the matrix failed until the last task landed.

**What this plan deliberately does not repeat.** The batch envelope, `_check_write_items`, `_batch_out`, the `_send`/`_check_scope`/`_receive` split, and the fake/real seam reasoning are all established in Block 2 and unchanged. Restating them would make this document look thorough while adding nothing an implementer cannot read in the code.

**One thing I expect to get wrong.** The cross-state validation (§4) is the first rule that cannot be checked locally, and the temptation will be to pre-check it anyway by fetching the stored question first. Do not: that turns one batch call into N+1 requests and still races. Let it fail per-item.
