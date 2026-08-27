# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.8.0] — 2026-08-27

**First release. Full parity with Skilljar's official MCP server — all 73 of its tools,
asserted by `tests/test_parity.py` rather than claimed — plus pagination on every listing
that supports it, capability gating, and a local scope pre-check.**

Collapses the six versions the roadmap had assigned to Blocks 2–9 (v0.1.0–v0.8.0) into
one, because none of them was ever published: the release was blocked on a v2 credential
(`WAITING-FOR-002`, closed 2026-08-27) while the blocks landed behind it. The number is
the one the roadmap gave to parity-complete, which is the honest description of what this
is — a working, complete, pre-1.0 surface.

**Writes are implemented but unproven against Skilljar.** No write tool has ever run
against a real organization, and `tests/integration/` is enforced read-only until
`WAITING-FOR-003` closes. That blocks confidence, not delivery, and is stated here so the
absence is not mistaken for an absence of testing.

What follows is the per-block detail, newest first.


### Fixed
- **Five list tools never paginated.** `list_groups`, `list_visibility_overrides`,
  `list_signup_field_values`, `list_published_courses` and `list_domains` read `has_more`
  and `next_cursor` out of `meta`. Real Skilljar — and `FakeBackend`, which matches it —
  put both at the **top level** of the envelope; `meta` carries only `page_size`. So all
  five always reported `has_more: false` and never emitted a cursor: a caller was told
  "that is everything" after one page. Confirmed against live Skilljar, where
  `list_domains` returned one row and claimed there were no more.
- Introduced in Blocks 7–9. The eight earlier list tools read the envelope correctly,
  which is why it looked like a working pattern.
- **Nothing caught it because the per-block tests asserted `has_more is False` on
  single-page fixtures** — an assertion that passes whether the code works or not. A test
  that can only observe the value the bug produces is not a test of it.

### Added
- **`tests/test_pagination.py`** — one fixture deep enough to force a second page, driven
  through the real tools, for every paginated tool at once: first page reports more and
  offers a cursor, the cursor advances, the last page says so. Plus the inverse for the
  three tools Skilljar does not paginate, which must not grow paging arguments they
  cannot honour.
- It is **fail-closed**: a list tool that appears in neither the paginated nor the
  unpaginated set fails the classification test, so the next one is covered without
  anyone remembering.

### Added
- **The integration suite can no longer write to a real organization.** Its conftest
  claimed "everything here is READ-ONLY" for several blocks and nothing enforced it —
  the suite was read-only by habit, and a habit is not a control. `live_client` is now
  wrapped in `ReadOnlyClient`, which is **fail-closed**: a method absent from a
  hand-written allowlist raises before anything reaches the network, so a tool added
  next block is refused by default.
- The allowlist is hand-written rather than derived from `policy._GATES`, and two tests
  assert the two AGREE without either being built from the other. Deriving it would make
  the control agree with a mislabelled gate instead of checking it.
- Verified by adding a rogue test calling `create_courses` against live Skilljar and
  watching it refuse; and by three mutations — unwrapping the fixture, and sneaking a
  write method onto the allowlist, both caught.
- **`WAITING-FOR-003`** records the open question behind this: where may this project
  write? The only organization these credentials reach is CSA's production one, with
  42,669 real learners. It carries the questions for Hannah and notes that the dev
  client still holds four authoring write scopes that nothing currently needs.

### Added
- **`scripts/mcp-launch.sh`** — reads `CSA_SKILLJAR_*` from a `.env` file and execs the
  server, so an MCP client can be pointed at it and the client configuration holds no
  secret. `claude mcp add -e KEY=value` writes the literal value into `~/.claude.json`,
  which is neither gitignored nor a secrets store, and puts it in shell history on the
  way.
- It **parses** the file rather than sourcing it. `source` executes the file: a stray
  `echo` in `.env` would print to stdout and corrupt the JSON-RPC stream before the
  server started, and any other command in it would simply run. Both are regression
  tests, and reverting to `source` kills three of them.
- Only `CSA_SKILLJAR_*` names are exported — this repository's own `.env` also holds a
  v1 testing key that is not the server's to receive — and an already-exported variable
  wins over the file, so a one-off override needs no edit to the credential file.

### Fixed
- **The scope pre-check refused every call against a real token.** Skilljar issues
  granted scopes in a **`scopes`** claim holding a JSON **list**; this code read the
  RFC 6749 / RFC 9068 standard `scope`, a space-delimited string. So `granted_scopes()`
  returned empty for every production token, and every scoped v2 call was refused with
  "Your v2 client was issued: (none). Re-issue it including `courses:read`" — against a
  client that had been issued seventeen scopes correctly. Both claim names and both
  shapes are now read.
- The offline suite was green throughout, because its JWT fixture could only produce
  `scope` as a string — the shape the code already expected. **A fixture that can only
  express your own assumption cannot catch a mismatch with the vendor.** The helper now
  takes arbitrary claims, and the vendor's real shape is recorded next to the tests.
- **"No scope claim" and "no scopes" are now different answers.** `granted_scopes()`
  returns `None` when the token does not declare its scopes, and `()` only when it
  declares none. Collapsing them meant an unrecognised claim silently refused everything
  and blamed the credential — the same absorbing-state shape as the `_expired` bug in
  ZERO-DEFECT §17. `check_access` reports `scopes_unknown` rather than an empty list.

### Fixed
- **ADR-003 cited evidence that does not hold.** It said the API's authorization server
  "does offer `client_credentials`". It does not advertise it — `grant_types_supported`
  lists only `authorization_code` and `refresh_token`, the same as the hosted MCP
  server's. The decision is still correct, but the evidence is now a probe: the token
  endpoint returns `401 invalid_client` for `client_credentials` with fake credentials
  (the grant was accepted and reached the credential check), while a nonsense grant type
  returns `400 invalid_request` and the validator names `client_credentials` first among
  the three it accepts. An ADR whose stated reasoning fails when checked is worse than
  one that says less.
- This is the mirror image of the discrepancy already recorded in `CLAUDE.md` — 88
  scopes advertised against 28 implemented. There the vendor's metadata runs ahead of
  the API; here it runs behind. Probe beats docs in both directions, the vendor's own
  machine-readable docs included.

### Added
- `scripts/check_upstream.py` now probes the `client_credentials` grant on every drift
  check. It needs no credentials — `401 invalid_client` and `400 invalid_request`
  separate "grant accepted" from "grant withdrawn" — and if Skilljar ever withdraws it,
  this server cannot authenticate at all, since there is no browser here to run
  `authorization_code` through.

### Fixed
- **`serverInfo.version` was an empty string** in the MCP initialize handshake — the
  field a client shows when someone asks which build they are talking to. `MCPServer`
  was constructed without `version`. No in-process test reads the handshake, so nothing
  caught it until a stdio smoke test looked.

### Added
- **`tests/e2e/` — the first tests that drive the installed console script as a
  subprocess over stdio**, the way a real MCP client does. Everything else builds the
  server in-process, which cannot see the initialize handshake, what reaches stdout, or
  whether the console script is wired up at all. Three real defects have hidden in that
  gap.
- The stdout-purity check (CLAUDE.md invariant 1) runs in the fixture teardown, so every
  e2e test asserts it regardless of what it was written to exercise. Getting it to work
  took three attempts, each failing silently:
  1. Reading stdout only up to the last response missed a stray `print()`, because
     `print()` to a pipe is BLOCK-buffered and the bytes sit in the buffer past every
     response the test read.
  2. Reading the buffer at exit still missed it, because `terminate()` sends SIGTERM and
     tears the process down WITHOUT flushing. The test now closes stdin and waits for a
     graceful exit, which is what flushes.
  3. `shutil.which` resolved the console script through PATH and found a **stale pipx
     install from an earlier release** — eight tools missing, wrong version, every
     assertion reporting on software that is not this checkout. The script is now
     resolved next to the test interpreter, and one test asserts the subprocess imports
     `csa_skilljar` from this repository.
- A missing console script is a loud collection error rather than a quiet skip, because
  any editable or wheel install provides it and a suite that skips itself reports green
  while testing nothing (ZD-17). `CSA_SKILLJAR_NO_E2E=1` opts out deliberately.

### Added
- **Block 9 — web packages and client registration. PARITY COMPLETE.** Six tools, and
  the last of the official server's 73. `tests/test_parity.py` now asserts the diff:
  73 of 73 present, zero missing, three declared extras of our own.
- Web packages are the only ASYNCHRONOUS family. `create_web_packages` queues an
  outbound fetch and returns rows in state PROCESSING; a malformed archive surfaces
  later as state ERROR and never as a failure on the create call. The description says
  so explicitly, because a model that reports "uploaded" here is reporting on a job that
  has not run.
- `create_web_packages` deliberately does NOT deduplicate on `content_url` — every other
  create tool here does, and two identical URLs are a legitimate request for two
  packages.
- `update_web_packages` refuses `type`, `state`, `base_path` and `display_name`. Skilljar
  accepts them and silently ignores them, which is unusual for this API and exactly
  ADR-008's case.
- `update_web_packages` warns that a rename can look like it did nothing: `display_name`
  is derived and only tracks `title` once the package reaches READY.
- `delete_web_package` takes one id rather than a batch, because its conflict outcome
  has no home in a per-row result: deleting a package a live lesson still uses is
  refused outright.
- `register_oauth_client` is the only UNAUTHENTICATED call in the server and the only one
  that returns a credential. It is routed through a dedicated `_register` path rather
  than `_send`, so the organization's bearer token is never sent to a registration
  endpoint that does not want it — and so the call works when no credential is
  configured, which is the situation someone registering a client is in. RFC 7591's
  `{error, error_description}` shape is surfaced rather than collapsed to a status code.
  It is off unless the `admin` profile is named, though Skilljar's own server ships it
  enabled.
- New `webpackages.read` / `webpackages.write` capabilities; the `authoring` profile
  grants both, since packages are authoring material.

### Fixed
- `get_certificate` returned only status and timestamps, dropping `code` — the public
  verification code, which is the thing a learner or employer actually quotes — and
  `score_as_percent`. Both are now returned, and the description explains that a null
  score means "not recorded", not zero. Found by the new parity test's
  minimum-description check rather than by anyone reading it.
- **`scripts/verify.sh` was weaker than CI.** CI runs `bandit` and `pip-audit` in a
  `security` job; verify did not, so the pre-commit gate passed green while CI failed —
  the same class of problem the script was written to prevent. Both now run locally, and
  both tools moved into the `dev` extra so CI and verify use the same versions. Verified
  by reintroducing a finding and watching verify fail.
- Three `bandit` B105/B107 `hardcoded_password` hits, all name-heuristic false positives
  on RFC 7591 vocabulary. One was fixed honestly by renaming `_SECRET_WARNING` to
  `_SHOWN_ONCE_WARNING`; the other two are annotated, because `token_endpoint_auth_method`
  is Skilljar's own parameter name and ADR-006 forbids renaming it. Recorded in
  `SECURITY-RESOURCES.md` with counter-evidence tests, including one that refuses a bare
  `# nosec` anywhere in `src`.
- A new `ConflictError` would have reached the MCP client as `UnexpectedToolError` with
  its **message discarded** (CLAUDE.md invariant 2). Added its translation clause, a
  base-class backstop so a future subclass degrades to readable rather than silent, and
  `tests/test_error_translation.py`, which walks `SkilljarError.__subclasses__()` so a
  new error type is covered the moment it is defined.

### Added
- **Block 8 — publishing and catalog.** Twelve tools, and the first whose effects are
  visible to the anonymous public: publishing puts a course on a customer-facing domain,
  `open_access` allows anonymous access, and `visible_on_catalog` lists it publicly.
- A new `publishing.read` / `publishing.write` capability pair. `publishing.write` is in
  no profile but `full` — notably not in `authoring`, so a credential that can write
  lesson HTML cannot ship it to the internet.
- The three visibility-override tools are gated by `groups.*`, not `publishing.*`.
  Upstream hangs them off `/v2/groups/{id}/relationships/published-course-visibility/`
  and requires `student-groups:write`; gating by the scope the credential actually needs
  keeps the local gate and the remote one in agreement.
- `update_published_courses` refuses `slug`, `course_id` and `domain_id` rather than
  passing them on. Skilljar accepts all three and silently ignores them, which is
  exactly the case ADR-008 exists for.
- `unpublish_published_course` frees the slug and `republish_published_course`
  reassigns it, so a course can return at a different public URL. Both descriptions say
  so, and a regression test asserts the slug can change across the cycle.
- `delete_published_course` is documented as what it is — a soft unpublish, near-identical
  to `unpublish_published_course`, named after v1's DELETE verb rather than its effect.
  Each tool points at the other so a model is not left guessing which was meant.
- `add_visibility_overrides` documents that the unique key includes `is_visible`, so an
  allow row and a block row for the same course coexist rather than replacing each other.
- `remove_visibility_overrides` echoes the request's `published_course_id` rather than
  the override's own id, reproducing upstream's deliberate choice so results correlate to
  inputs without a second lookup.
- `publish_courses` documents the two booleans that default TRUE
  (`require_all_prerequisites`, `unique_progress_per_enrollment`) against ten that
  default false, and that a duplicate publish is a per-item conflict rather than a
  batch failure.

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
