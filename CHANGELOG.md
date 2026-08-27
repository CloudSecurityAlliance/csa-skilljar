# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Block 4 — question banks and bindings.** Nine tools. Reusable exam item pools, and
  the quiz-to-bank binding that makes them reusable — neither of which v1 can do.
- Re-binding an already-attached bank is an idempotent **partial** update: omitted fields
  keep their stored values and an omitted `order` is not re-derived.
- `delete_question_banks` states in its description that deleting a bank silently unbinds
  every quiz using it, while leaving those quizzes alive.

### Added
- **Block 3 — quizzes and questions.** Ten tools, and the project's first destructive
  operations (`delete_quizzes`, `delete_questions`).
- A new `content.delete` capability, deliberately separate from `content.write`: an
  authoring credential that can create and update content cannot destroy it. Off in every
  profile except `full`.
- Local encoding of the question quiz-XOR-bank rule, the per-type answer-shape rules, and
  the fields the service assigns rather than accepts.
- Documented behaviour that exists only in the captured registry: `FILL_IN_THE_BLANK`
  forces every answer correct, answers are immutable on update, and deleting a quiz spares
  bank-owned questions.

### Added
- **Block 2 — courses and lessons.** Seven new tools: `get_course`, `create_courses`,
  `update_courses`, `list_lessons`, `get_lesson`, `create_lessons`, `update_lessons`.
- Batch writes over v2's `207` envelope, with per-item results preserved rather than
  collapsed into one status.
- Local validation that mirrors the API's document-level `422`: an invalid item rejects
  the whole call rather than writing part of it.
- The lesson type XOR rules (`HTML`/`MODULAR`/`QUIZ`), and a confirmation flag guarding
  the `content_items` tri-state where an empty list deletes every child.
- `tests/integration/` — the first live-Skilljar suite, gated on
  `CSA_SKILLJAR_INTEGRATION=1`, with a guard asserting the gate skips *for the right
  reason*.
- ADR-008: reject read-only fields the official server silently ignores.

### Added (Block 1)
- **Block 1 — a working server.** A local stdio MCP server over Skilljar's v2 API with four
  tools: `check_access` (which credentials work and what each unlocks),
  `describe_capabilities` (what exists but is not enabled), `report_a_problem` (a filable
  report carrying no ids and no credentials) and `list_courses` (one real read).
- `SkilljarClient` library with a `Backend` protocol seam, `V2Backend`, `FakeBackend`, and a
  conformance guard comparing all implementations signature-for-signature.
- Fail-closed `PolicyBackend`: a backend method with no declared gate is refused, not
  delegated. Named profiles (`parity` default, through `full`).
- OAuth `client_credentials` authentication with a local scope pre-check — an impossible call
  is refused by name, with no network traffic, using a scope table generated from the v2
  OpenAPI spec.
- `scripts/verify.sh`, `scripts/check_docs.py` (25 documentation claims asserted against the
  artifacts) and `scripts/gen_scopes.py`.
- Design spec: `docs/superpowers/specs/2026-08-26-csa-skilljar-design.md`.
- Upstream API snapshots in `specs/` — Skilljar v1 (OpenAPI 3.0.3) and v2 (OpenAPI 3.1.0),
  fetched 2026-08-26.
- Surface analysis in `analysis/` — a 66-entity reconciliation of both APIs, plus the
  live OAuth scope catalog.

119 tests, 96% coverage, offline with no network and no credentials.
