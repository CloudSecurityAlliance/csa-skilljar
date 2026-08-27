# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Block 7 — groups and signup fields.** Eleven tools. Groups decide which published
  courses a learner can see, so they are administered like content but grant access like
  people; they get their own `groups.read` / `groups.write` / `groups.delete`
  capabilities rather than borrowing either family's.
- `delete_groups` is gated by `groups.delete` alone, in no profile but `full`. A group is
  a **hard** delete — not a soft one like quizzes and banks — and its memberships and
  published-course visibility overrides cascade at the database, so deleting a group can
  revoke course access learners currently have.
- `update_groups` distinguishes an **absent** `category_id` from an **explicitly null**
  one: null clears the category, omitted leaves it alone. `rule_email_domains` replaces
  the stored array rather than merging, and the description says so, because the natural
  assumption silently deletes the caller's other domain rules.
- Group membership tools are annotated idempotent, which they genuinely are: adding an
  existing member succeeds and removing a non-member reports `deleted`. The result
  therefore cannot be used to test membership, and the tools say so rather than implying
  a change occurred.
- `create_signup_field_values` is an upsert wearing a `create_` name, with a hybrid
  envelope — `student_id` at the top level, per-field items in the batch. It keys items
  by the signup-**field** id while `update_signup_field_values` keys them by the
  signup-field-**value** id; both descriptions name the other call's identifier so a
  model holding one id can tell which it has.
- `get_signup_field_value` takes `signup_field_value_id`, not `id`. Every other
  single-object lookup takes `id`; this one matches Skilljar's parameter exactly, per
  ADR-006.
- Signup-field values are learner-typed free text and are labelled untrusted, the same
  treatment `list_course_ratings` and lesson HTML get.

### Fixed
- **ROADMAP's `updated_at` note was half the story.** It named `GroupAttributes` as the
  lone v2 resource spelling the timestamp `updated_at`. A survey of all fourteen
  `*Attributes` schemas found two: `GroupAttributes` and `VisibilityOverrideAttributes`,
  the latter a Block 8 tool. Corrected in place so Block 8 is not misled.
- ROADMAP listed the Block 6 tool as `set_password`; the captured registry says
  `set_student_password`. The code was built from the registry and was already correct.

### Added
- **Block 6 — students.** Eight tools, and the ones this project was most careful about:
  irreversible PII erasure, deactivation, and two password paths.
- A new `people.destructive` capability holding all four sensitive tools. It is granted by
  **no named profile except `full`** — the `people` profile, which an operator setting up
  learner administration would reach for, gives `people.read` and `people.write` and cannot
  touch erasure or passwords.
- `anonymize_student` and `set_student_password` refuse to run without `confirm=True`. This
  is a restatement gate, not an access control: it makes a destructive call legible to a
  human reading the transcript. The capability gate and the OAuth scope are the real
  controls.
- `anonymize_student` is the only call in the codebase that sends Skilljar's
  `X-Confirm-Destructive` header, and a test enumerates every other call to prove it.
- `update_students` refuses `is_inactive: false` combined with other fields, because
  Skilljar accepts that and silently drops the other fields. Reactivation takes two calls.

### Added
- **Block 5 — enrolment and reporting.** Nine tools, and the first that affect people
  rather than content. Both writes are gated on `enrolment.write`, which the `authoring`
  profile does not grant.
- `complete_enrollments` requires `send_notifications` with no default, because it decides
  whether real learners receive email.
- `list_course_ratings` returns learner-written free text and says so — the same
  attacker-influencable surface as lesson HTML.

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
