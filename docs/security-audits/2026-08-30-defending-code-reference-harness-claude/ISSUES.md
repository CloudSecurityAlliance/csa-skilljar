# Issues to file · audit 2026-08-30-01

Prepared before the audit branch merged so the permalinks resolve on landing.
**File these after the merge, not before** — the links point at paths that do not
exist yet.

Each issue is one verifiable done-condition. Full per-finding detail lives in
[`FINDINGS.md`](FINDINGS.md); bodies carry enough to act on and point back rather
than duplicating, so there is one copy of the analysis to keep correct.

**Permalink base** (all bodies use it):

```
https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/
```

Locations are `file:line` at `280c8e8`, read from a pinned worktree. Re-verify
against `main` before editing.

---

## Labels

| label | for |
|---|---|
| `security` | anything from a security audit |
| `audit:2026-08-30-01` | traceability — every issue from this audit carries it |
| `flaw` | exploitable; a defect, not a trade-off |
| `hardening` | reduces exposure; needs a precondition outside our control |
| `investigation` | answers a question before a fix can be designed |
| `supply-chain` | release pipeline, dependencies, packaging |
| `test-integrity` | a control that lives in the test suite |
| `documentation` | docs only |
| `tooling` | repo tooling and automation |
| `good-first-issue` | small, self-contained, low risk |

---

## 0 · Tracking issue

> **Title:** Security audit 2026-08-30-01 — remediation tracking
>
> **Labels:** `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> Tracking issue for remediation of audit `2026-08-30-01`
> ([record](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/README.md) ·
> [findings](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md) ·
> [threat model](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/THREAT_MODEL.md)).
>
> Audited `280c8e8` (v0.13.0) with Claude Code via the
> `anthropics/defending-code-reference-harness` `/threat-model` workflow, heavy
> human review, reading a **pinned detached worktree** so citations could not
> drift. 37 threats across 20 entry points.
>
> **The audit fixed nothing, deliberately** — the flaw trail and the fix trail are
> kept in separate contexts so both stay independently reviewable. Record the fix
> and its reasoning in `REMEDIATION.md` in the audit directory, not in these
> threads.
>
> **Read this before starting.** Five findings (#4, #5, #10, #11, #12) are one
> pattern: *a hand-maintained description of a policy drifting from the policy*.
> ADR-005 describes a registration layer that does not exist; `policy.py:27-30`
> states a delete/write split the table two entries down does not apply;
> `check_access` describes a credential state that cannot occur; `CLAUDE.md`
> describes a repository with no `src/`; `demo.py` queries a gate table with the
> wrong key type while `policy.py:207-209` documents that divergence two lines
> away. Five patches leave the sixth instance equally invisible — #13 is the one
> that closes the class.
>
> **Also worth knowing:** two hypotheses carried from the `csa-google-workspace`
> audit were **refuted** here (a read-annotated tool that mutates; a gate wrapping
> only one backend), and the release pipeline was already designed against that
> audit's worst finding. `README.md` §7 clears thirteen items with reasons.
>
> **Investigation first**
> - [ ] #1 Settle whether Skilljar sanitises `content_html` on render *(blocks #2)*
>
> **P1 — security**
> - [ ] #2 T1 — unsanitised HTML round-trips through the model into the learner portal
> - [ ] #3 T7 — no URL encoding anywhere; v1 has no local guard
> - [ ] #4 T8 — profile-gated tool registration does not exist
> - [ ] #5 T9 — the declared delete/write split is not applied; `authoring` can destroy
> - [ ] #6 T10 — the read-only integration guard is dead, and the obvious repair is worse
> - [ ] #7 T11 — one-directional conformance across a shared gate table
> - [ ] #8 T16 — `send_password_reset` has no confirm gate; three tools that email people are marked non-destructive
> - [ ] #9 T17 — `open_world_hint` is set on none of the 112 tools
>
> **P2 — description drift**
> - [ ] #10 T12 — `check_access` misreports credential state
> - [ ] #11 T33 — `demonstration_plan` predicts refusals from the wrong table keys
> - [ ] #12 T30 — `CLAUDE.md` says nothing is implemented
> - [ ] #13 Close the class: assert every hand-maintained description against the constants
>
> **P3 — hardening**
> - [ ] #14 T14 — `client.credentials` reaches around the capability gate
> - [ ] #15 T24/T26 — no `PROFILES` matrix; three unasserted "no default profile grants this" claims
> - [ ] #16 T25/T34 — no lockfile; raise the `setuptools` and `pytest` floors
> - [ ] #17 T27 — no retry, backoff or pagination ceiling
> - [ ] #18 T31/T29 — v1 families return raw upstream rows; learner-PII writes gated by `groups.write`
> - [ ] #19 T32/T37 — three tests that cannot fail, and the `ReadOnlyClient` underscore escape
> - [ ] #20 T22 — assert the externally-enforced controls
>
> **P4 — docs and tooling**
> - [ ] #21 Adopt the audit's threat model as the living `THREAT_MODEL.md`
> - [ ] #22 Generate the audit index from front matter

---

## Investigation

### 1 · Settle whether Skilljar sanitises `content_html` on render

> **Labels:** `investigation`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> Blocks #2. The whole rating of T1 depends on this and nothing in the repository
> can establish it. Vendor documentation is explicitly not trusted for it.
>
> **The test is a three-point observation:**
>
> ```
> [1] what we send → [2] what the API returns on read-back → [3] what the rendered page contains
>         └─ storage transformation ─┘        └─ render transformation ─┘
> ```
>
> The MCP server supplies legs 1 and 2. Leg 3 needs the published page fetched as
> an authenticated learner, or a headless browser. **Only having 1→2 gives false
> confidence in both directions** — a payload that survives storage but is escaped
> at render is a false positive; one transformed at storage into something worse at
> render (mXSS) is a false negative.
>
> **Safety requirements, not optional:**
>
> - An **isolated, unpublished course** on a non-production domain. A payload in a
>   published lesson is a live vulnerability you created.
> - **Guaranteed teardown, with proof.** Record what was created and assert it is
>   gone.
> - A payload that proves execution **without doing damage** — a callback to a
>   listener you control is unambiguous, logged, and inert if escaped. Better than
>   `alert()`.
> - Consider whether injection testing against Gainsight's platform needs their
>   authorization. This is a prerequisite question, not a formality.
>
> **Outcome:** if Skilljar sanitises, T1 drops to low and #2 becomes defence in
> depth. If it does not, #2 is remediation and the severity in the threat model
> stands.
>
> Detail: [`FINDINGS.md` §4.1](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

---

## P1 — security

### 2 · T1 · Unsanitised HTML round-trips through the model into the learner-facing portal

> **Labels:** `security`, `flaw`, `audit:2026-08-30-01`
>
> **Body:**
>
> Blocked by #1 — settle the premise before designing the fix.
>
> Six free-text HTML fields are accepted from the model and POSTed verbatim,
> validated for presence only: `content_html` and `description_html` on
> `create_lessons`/`update_lessons` (`lessons.py:218-266`, allowlist at `:38-45`),
> and four question HTML fields on `create_questions`/`update_questions`
> (`questions.py:214-262`).
>
> **There is no sanitisation anywhere in the repository:**
> `grep -riE "sanitiz|bleach|html\.escape|nh3" src/` → **0 hits**.
>
> **The chain:** `get_lesson` returns untrusted author HTML into model context —
> and says so at `lessons.py:206` → the operator asks the agent to revise,
> translate or duplicate a lesson → `create_lessons` writes model-produced HTML
> back → `publish_courses` puts it on a customer-facing domain → it renders in
> every learner's browser who opens that lesson.
>
> **Bounds:** the portal is sign-in gated beyond course descriptions, so this
> executes for authenticated learners rather than drive-by anonymous.
> `content.write` is absent from the default `parity` profile.
>
> **Fix options:** a tag/attribute allowlist on the write path, or refusing
> `content_html` from a model altogether and requiring a human-authored body — the
> second is smaller and arguably correct for an agent tool.
>
> **Do this regardless of #1's outcome:** add the untrusted-data warning to the
> **write** side. It exists on the read side and says nothing about what the write
> tools write into. That asymmetry is how the chain stayed invisible.
>
> **Acceptance:** a test asserts a `<script>` payload submitted through
> `create_lessons` is either rejected or neutralised, and the write-side tool
> descriptions state what they are writing into.
>
> Detail: [`FINDINGS.md` §4.1](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 3 · T7 · No URL encoding anywhere, and the v1 path has no local guard

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `grep "quote(\|urlencode" src/` returns exactly one hit — a `Content-Type`
> header string. There is no URL encoding in the codebase.
>
> **Query concatenation**, the only such site in either backend
> (`backend.py:1870-1873`):
>
> ```python
> f"/v2/students/{student_id}/send-password-reset/?domain={domain}"
> ```
>
> `domain` is unvalidated free text from the tool boundary (`students.py:281`).
> CWE-88. Every other call passes `params=` to httpx, which encodes.
>
> **Path interpolation**, ~41 sites. Two interpolate free-text *names* rather than
> ids — `v1backend.py:286` and `:291`, reached from `paths.py:117` and `:144`.
> httpx removes dot-segments per RFC 3986, so `../` reaches a different endpoint
> on the same host with the credential attached.
>
> **Why v1 is the sharp side.** On v2, `_check_scope` at least validates the static
> `template`. **On v1 there is neither a scope pre-check nor a known-operation
> guard** — and the v1 credential is the organization-wide Basic key with no scopes
> and no expiry. A crafted `domain_name` sends the most powerful credential in the
> system to an endpoint the capability gate never authorised.
>
> Note this also decouples the local control from the wire: `_check_scope`
> authorizes the *template* while the URL sent is built from the interpolated
> string, so "refuse an impossible call locally with zero network traffic" does not
> cover what actually goes out.
>
> **Fix:** percent-encode every interpolated segment; reject ids containing `/`,
> `?`, `#` or `%` at the tool boundary; add a known-operation guard to `V1Backend`
> matching v2's.
>
> **Acceptance:** a test asserts a path parameter containing `../` is rejected
> before any request is constructed, on both backends.
>
> Detail: [`FINDINGS.md` §4.3](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 4 · T8 · Profile-gated tool registration does not exist

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> ADR-005 describes two layers. Layer 2 (`PolicyBackend` controlling execution) is
> real and fails closed. **Layer 1 — the profile controlling registration — is not
> implemented.** `mcp/server.py::create_server` calls all 23 `register_*_tools`
> producers unconditionally, and none receives the policy or profile; only
> `access` and `feedback` take `settings`, for reporting rather than gating.
>
> So in a default `parity` install **all 112 tools are registered and visible to
> the model**, including `anonymize_student`, `set_student_password`,
> `delete_groups` and `rotate_oauth_client_secret`.
>
> **What it falsifies:** `SECURITY.md`'s *"An install exposes a profile, not the
> whole surface"* is false as written, and ADR-005's context-cost rationale
> (~12k tokens of always-on context) is not being realised.
>
> **Why it is more than tidiness:** the project's own defence hierarchy ranks
> server instructions last. Injected lesson content is addressing a model that can
> *see* the destructive tool names and argument shapes.
>
> **Fix:** thread the policy to each producer and skip families the profile cannot
> reach. **Keep `describe_capabilities` registered regardless** — ADR-005's own
> self-review found that a tool the model cannot see becomes a capability the user
> never learns exists. Make that carve-out explicit.
>
> **Acceptance:** a test asserts the registered tool count under `parity` is
> strictly less than under `full`, and that `describe_capabilities` is present in
> both.
>
> Detail: [`FINDINGS.md` §4.2](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 5 · T9 · The declared delete/write split is not applied; `authoring` can destroy

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `policy.py:27-30` states the principle: *"Deletes are gated separately from
> writes on purpose: an authoring credential that can create and update content
> should not thereby be able to destroy it. No default profile grants this."*
>
> Verified against the table:
>
> ```
> policy.py:75   "authoring": (READ_CONTENT, WRITE_CONTENT, READ_WEB_PACKAGES, WRITE_WEB_PACKAGES)
> policy.py:164  "delete_web_package": WRITE_WEB_PACKAGES
> policy.py:116  "unbind_banks":       WRITE_CONTENT     # tool annotated DESTRUCTIVE
> policy.py:149  "delete_published_course":    WRITE_PUBLISHING
> policy.py:150  "unpublish_published_course": WRITE_PUBLISHING
> ```
>
> **The shipped `authoring` profile can delete web packages and unbind question
> banks** — the exact thing the split exists to prevent. The publishing pair is
> latent only because just `full` grants `publishing.write`; adding a "publisher"
> profile would bring taking a live course off a customer-facing domain with it.
>
> **Root cause:** there is no `publishing.delete` or `webpackages.delete` in
> `ALL_CAPABILITIES` (`policy.py:63-68`) to gate them with.
>
> **Fix:** add the two capabilities, move the four gates, and pair it with #15 so
> the next instance is catchable. Note `unbind_quiz_question_banks` is already
> annotated `DESTRUCTIVE` at the tool layer — the tool vocabulary and the
> capability table already disagree.
>
> **Acceptance:** a test asserts `DELETE_*` capabilities appear in no profile but
> `full`, directly rather than by derivation.
>
> Detail: [`FINDINGS.md` §4.4](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 6 · T10 · The read-only integration guard is dead, and the obvious repair is worse than the defect

> **Labels:** `security`, `test-integrity`, `audit:2026-08-30-01`
>
> **Body:**
>
> **Read the fix instruction before touching the allowlist.**
>
> The guard is well designed — `ReadOnlyClient` fails closed and
> `READ_ONLY_METHODS` is hand-written *specifically* so it is a second opinion
> rather than a derivation (`conftest.py:40-43` explains why). Two things broke it.
>
> **The allowlist drifted.** 57 methods in `_GATES` carry a `READ_*` capability;
> `READ_ONLY_METHODS` (`tests/integration/conftest.py:44-53`) lists 30. **27 are
> missing**, including `list_vilt_registrations`, `list_ilt_instructors`,
> `find_learner`, `get_asset`, `get_purchase`, `list_webhooks` and
> `list_learner_progress`.
>
> **The assertion never runs.** `pytest_collection_modifyitems`
> (`conftest.py:23-37`) skips every item in the directory unless
> `CSA_SKILLJAR_INTEGRATION=1` — including the four pure-unit consistency guards
> that need no network and no credentials.
>
> **Why the repair path is the hazard.** The first person to enable integration
> gets a red suite. The obvious fix is pasting 27 names into the allowlist — which
> would authorise live reads of `list_vilt_registrations` (learner name and email
> on every row) and `list_ilt_instructors` against the production organization the
> same file documents as holding 42,669 real learners.
>
> **Fix, in this order:** (1) move the four `_GATES`-versus-allowlist consistency
> tests **out** of `tests/integration/` so they run in CI with no network and no
> credentials. (2) *Then* reconcile the 27-entry drift deliberately, deciding per
> method whether a live read of it is acceptable — which is the decision the
> hand-written list exists to force.
>
> **Acceptance:** the consistency tests run in default CI, and the two tables
> agree without either being derived from the other.
>
> Detail: [`FINDINGS.md` §4.5](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 7 · T11 · One-directional conformance across a shared gate table

> **Labels:** `test-integrity`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> `tests/test_backend_conformance.py:10-24` compares protocol → implementation
> only:
>
> ```python
> missing = {n for n in dir(Backend) if not n.startswith("_")} - set(dir(impl))
> ```
>
> A method on `FakeBackend` or `V2Backend` but **absent from the protocol** passes
> clean. The gap is already occupied benignly: `FakeBackend.group_members`
> (`backend.py:1098-1100`) exists on the fake, not the protocol. Counts: protocol
> 81 public methods, `FakeBackend` 82, `V2Backend` 81.
>
> **Why it compounds.** Three further guards also key off `dir(Backend)` — the
> `_GATES` completeness check (`test_policy.py:14`), the v1/v2 duplication check
> (`test_parity.py:105`), and the ADR-002 overlap check (`test_progress.py:149`).
> A method added to `V2Backend` but not the protocol escapes **all four**. And
> because `_GATES` deliberately spans both backends, such a method sharing a v1
> name (`list_labels`, `list_webhooks`, `get_purchase`) would be reachable under
> whatever capability the **v1** entry declares.
>
> **Also:** `IMPLEMENTATIONS = [FakeBackend, V2Backend]` — the
> `V1Backend`/`FakeV1Backend` pair has no conformance test in either direction.
>
> **Fix:** add `set(public(impl)) - set(dir(Backend))` must be empty or explicitly
> allowlisted, with `group_members` as the single entry; add a conformance test for
> the v1 pair.
>
> Detail: [`FINDINGS.md` §4.6](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 8 · T16 · `send_password_reset` has no confirm gate, and three tools that email real people are marked non-destructive

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `send_password_reset` (`students.py:281-299`) is the only one of four
> `people.destructive` tools with **no `confirm` gate** — its two peers
> `anonymize_student` and `set_student_password` both require one — and it is the
> easiest of the four for injected text to reach ("email everyone in group X a
> reset link"). Its `destructive_hint=True` is also the wrong shape: it destroys
> nothing, it contacts a third party.
>
> Separately, `complete_enrollments` (`enrolment.py:302`) and
> `bulk_enroll_students` (`:341`) both cause Skilljar to email real learners and
> are annotated `destructive_hint=False`; `add_group_memberships`
> (`groups.py:278`) grants course access under `IDEMPOTENT_WRITE`, the least
> alarming label in the file.
>
> **The repo's own risk model already disagrees with its annotations.**
> `demo.py:52-77` excludes all three by name with written reasons — *"enrols real
> people, who then receive email"*, *"marks real learners complete"*, *"puts real
> learners into a group, which can grant course access"*. That exclusion list is
> the natural source of truth for a corrected annotation pass.
>
> **Fix:** add `confirm=True` to `send_password_reset`; re-shape the annotations
> together with #9.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 9 · T17 · `open_world_hint` is set on none of the 112 tools

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `mcp/_tools/_base.py:15-22` defines four `ToolAnnotations` constants
> (`READ`, `WRITE`, `DESTRUCTIVE`, `IDEMPOTENT_WRITE`); none sets
> `open_world_hint`, and no tool overrides. Verified: zero `open_world` hits
> repo-wide.
>
> The MCP spec's default is **true**, so this is wrong in both directions:
>
> - `describe_capabilities`, `report_a_problem` and `demonstration_plan` touch no
>   network at all and advertise as open-world.
> - `send_password_reset` (emails a real person), `complete_enrollments` with
>   notifications, `bulk_enroll_students`, `create_web_packages` (queues an
>   outbound Skilljar fetch to a model-supplied URL) and `register_oauth_client`
>   (unauthenticated call to an endpoint binding no organization) carry the same
>   annotation shape as `list_courses`.
>
> A client using annotations to drive auto-approval currently cannot tell a closed
> org-internal read from a tool that contacts third parties.
>
> **Fix:** set `open_world_hint=True` on the five genuinely open-world tools and
> `False` on the three purely local ones.
>
> **Acceptance:** a test asserts every tool that reaches a third party declares
> `open_world_hint=True`, hand-written rather than derived.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

---

## P2 — description drift

### 10 · T12 · `check_access` misreports credential state

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `ClientProvider.__call__` raises `CredentialsMissing` at `_config.py:133-138`
> **before** the v1 backend is constructed at `:146-149` — so a **v1-only install
> can call no tool at all**, including the v1-only ones.
>
> Yet `check_access` reports `v1: configured=True` with the detail *"No v1-backed
> tools are implemented yet, so this is not currently needed"* (`access.py:46-48`),
> and `cli.py:35` says `(no v1 tools yet)`. Both are stale since Block 11 shipped
> seven v1-backed families: progress, assets, commerce, paths, events, vILT,
> taxonomy.
>
> This is the tool the server `INSTRUCTIONS` designates as the trusted diagnostic
> when everything else fails (`server.py:37-40`).
>
> **Fix:** correct both strings, and decide whether a v1-only configuration should
> work at all — if it should, the provider needs to construct the v1 backend
> independently of the v2 credential.
>
> Detail: [`FINDINGS.md` §4.7](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 11 · T33 · `demonstration_plan` predicts refusals from the wrong table keys

> **Labels:** `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `demo.py:460` does `P._GATES.get(step["tool"])` — but `_GATES` is keyed by
> **backend method name** while `step["tool"]` is the **MCP tool name**, and
> `policy.py:207-209` documents that divergence two lines from an affected entry:
>
> > `# Gated by the BACKEND method name; the tool is called`
> > `# `preview_event_payload`, which is the compression of ten endpoints.`
>
> Verified: `preview_event_payload` → **0** occurrences in `policy.py`;
> `get_sample_event_payload` → 1. Same for `list_quiz_question_bank_assignments`
> (0) versus `list_bank_assignments` (1). Both `.get()` calls return `None`, so
> those steps are predicted **not refused** — and `events.read` is not in the
> default profile, so the first demo run walks a narrator into the refusal the tool
> exists to prevent.
>
> Fails in the safe direction, but the coverage report is not derived from what it
> claims to be derived from.
>
> **Also:** `demo.py:444` reaches into the private `app._tool_manager._tools`.
>
> **Fix:** a documented tool-name→method-name mapping, asserted complete against
> the registry, rather than querying `_GATES` with the wrong key type.
>
> Detail: [`FINDINGS.md` §4.7](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 12 · T30 · `CLAUDE.md` says nothing is implemented

> **Labels:** `documentation`, `audit:2026-08-30-01`
>
> **Body:**
>
> `CLAUDE.md` — the agent behavioural contract every AI session loads — states:
>
> > *"Status: design complete, nothing implemented. The repository holds the design
> > spec, upstream API snapshots, and surface analysis. **Do not describe features
> > as working; there is no `src/` yet.**"*
>
> At a commit shipping **112 tools, ~10,200 lines and v0.13.0**. It also says
> "seven technical decisions" where there are eight.
>
> Three further status claims contradict each other — README banner v0.9.0, TODO
> v0.8.0, actual `__version__` 0.13.0 — and the changelog stops at Block 14 while
> Blocks 15–17 and `demonstration_plan` have shipped.
>
> This is exactly the failure mode `CHATGPT.md` and `GEMINI.md` refuse to risk:
> *"a stale guidance file misleads silently, which is worse than having none."*
> Operationally significant because multiple AI sessions work this repository.
>
> **Fix:** bring it current, and pair with #13 so it cannot silently rot again.
>
> Detail: [`FINDINGS.md` §4.7](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 13 · Close the class: assert every hand-maintained description against the constants

> **Labels:** `tooling`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> #4, #5, #10, #11 and #12 are five instances of one pattern: **a hand-maintained
> description of a policy drifting from the policy.** Five patches leave the sixth
> instance equally invisible.
>
> The repository already has the technique — `tests/test_descriptions.py` enforces
> a hand-written description contract per tool, fail-closed so a new tool with no
> entry fails. Extend it:
>
> - `check_access` and `cli.py` strings must agree with the shipped tool families.
> - `CLAUDE.md`'s stated version and module claims must agree with the tree.
> - Every `SECURITY.md` claim about profile behaviour must be asserted somewhere,
>   or removed.
> - `demo.py` must resolve gates through a documented mapping, not by querying
>   `_GATES` with the wrong key type.
>
> `scripts/check_docs.py` is the natural home. Note it is also the one guard script
> with **no tests of its own**, unlike `check_artifact.py` and
> `check_upstream.py` — both of which got test files precisely because untested
> guards misfired (#19).
>
> Detail: [`FINDINGS.md` §5.1](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

---

## P3 — hardening

### 14 · T14 · `client.credentials` reaches around the capability gate

> **Labels:** `security`, `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> `PolicyBackend.__getattr__` deliberately refuses underscore-prefixed names
> (`policy.py:263-264`) — but `_backend` is assigned in `__init__` (`:256`), so it
> lives in the instance `__dict__` and `__getattr__` never fires:
>
> ```python
> # client.py:41-42
> inner = getattr(self._backend, "_backend", self._backend)
> return getattr(inner, "_creds", None)
> ```
>
> This walks straight past the gate to the raw `V2Credentials` object, handing the
> caller `token()`, `granted_scopes()` and the id/secret fields. The underscore
> refusal is not doing the work it appears to do, and any future method added near
> `_creds` is ungated by construction.
>
> Callers today are `check_access` and `demonstration_plan`, both read-only, and
> `check_access` legitimately must answer when nothing is configured.
>
> **Fix:** return the presence and scope *shape* `check_access` actually needs
> rather than the credential object.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 15 · T24/T26 · No `PROFILES` matrix, and three unasserted "no default profile grants this" claims

> **Labels:** `test-integrity`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> `_GATES` gets the full treatment: a hand-written capability→method matrix with a
> comment forbidding derivation (*"deriving it tests the table against itself and
> passes no matter what the table says"*), cross-checked for completeness.
> **`PROFILES` gets no equivalent** — only a check that every name is a known
> capability (`test_policy.py:344-346`) and one comparison derived from the table
> it tests (`test_config.py:92-96`).
>
> Consequence: adding `WRITE_CONTENT` to `parity` breaks existing tests; adding
> `DELETE_CONTENT` or `DESTRUCTIVE_PEOPLE` to `parity` or `operations` **breaks
> nothing**. The three `policy.py` claims *"No default profile grants this"*
> (`:28-29`, `:39-41`, and the `people.destructive` equivalent) are unasserted.
> `tests/test_credentials.py:48` parametrises four of five non-admin profiles —
> `reporting` is never checked for `admin.credentials`.
>
> **Also (T24):** `_check_scope` skips entirely when the token declares no scopes
> (`backend.py:1565-1572`) — fail-open by design and documented, but no test
> exercises that path. This is the seam that produced three defects in four days.
>
> **Fix:** a hand-written `PROFILES` matrix mirroring the `_GATES` treatment,
> including the comment; assert the three claims directly; add a test for the
> scope-less-token path. This is what makes #5 catchable next time.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 16 · T25/T34 · No lockfile; raise the `setuptools` and `pytest` floors

> **Labels:** `hardening`, `supply-chain`, `audit:2026-08-30-01`
>
> **Body:**
>
> **No lockfile, no hash pinning, every constraint an open `>=` floor with no upper
> bound** — including the release build that produces the published artifact. Two
> clean installs a week apart can resolve differently.
>
> Note the repository's own asymmetry: GitHub Actions **are** SHA-pinned with
> Dependabot moving them, on the stated reasoning that *"a pin is only a control if
> something moves it."* Python dependencies get neither. And `pip-audit` audits the
> *installed* environment, so it structurally cannot see the PEP 517
> build-isolation environment where `setuptools` lives — the one dependency with a
> live overlapping advisory is the one the security gate cannot inspect.
>
> **Three paper overlaps, all unreachable as deployed** (full chain in
> `README.md` §6.2): `setuptools>=77` against CVE-2026-59890 (`<83.0.0`, macOS
> filesystem specific — releases build on `ubuntu-latest`) and CVE-2025-47273
> (`<78.1.1`, legacy `easy_install` path); `pytest>=8` against CVE-2025-71176
> (`<9.0.3`, dev only).
>
> **Fix:** raise `setuptools>=83` and `pytest>=9.0.3` — declaration-layer hygiene,
> zero runtime risk. Add a hash-pinned lockfile for the CI and release
> environments only, leaving the published package's ranges permissive.
>
> **Separately:** `check_artifact.py:64` runs `fnmatch` on a lowercased basename
> with **no Unicode normalization**, so an NFD-composed `.env` variant would match
> neither the exclusion nor the guard. Normalise before matching.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 17 · T27 · No retry, backoff or pagination ceiling

> **Labels:** `hardening`, `audit:2026-08-30-01`
>
> **Body:**
>
> Verified: **no 429 handling, no `Retry-After`, no backoff and no client-side
> throttle exists anywhere in `src/`** — only prose in `INSTRUCTIONS` and
> `access.py` telling the model not to retry.
>
> Amplifiers: `list_learner_progress` (`v1backend.py:169-176`) and
> `list_course_ratings` (`enrolment.py:243-247`) are **unpaginated**, and v1
> honours `page_size=1000` against 13,708 promo codes. Partial mitigations are
> per-family hand-chosen page caps (commerce 25/250, vILT the same, events
> likewise) rather than a shared control.
>
> **Fix:** retry with backoff honouring `Retry-After` on both backends; a shared
> page-size ceiling; pagination on the two unpaginated tools.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 18 · T31/T29 · v1 families return raw upstream rows; learner-PII writes gated by `groups.write`

> **Labels:** `hardening`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> **T31.** Every v2 tool flattens through an explicit field allowlist. Five v1
> families do not — `commerce.py:44`, `paths.py:34`, `taxonomy.py:31`,
> `vilt.py:33`, and `get_purchase` return **raw upstream rows**. So the redaction
> discipline that correctly catches webhook secrets and presigned URLs is
> per-family opt-in rather than structural: a new upstream field on a purchase or a
> registration row lands in a transcript by default, with nobody having decided.
> This is on the side with the least defence in depth.
>
> **T29.** `create_signup_field_values`/`update_signup_field_values` overwrite a
> learner's own registration answers and are gated `groups.write` rather than
> `people.write` (`policy.py:143-144`). Nothing is exposed today because the
> `people` profile grants both — but the capability boundary does not match the
> data, so any future groups-only profile would silently acquire the ability to
> rewrite learner PII. `demo.py` excludes these tools as *"overwrites a real
> learner's registration answers"*.
>
> **Fix:** explicit field allowlists on the five v1 families; re-gate the
> signup-field writes to `people.write` or a dedicated capability.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 19 · T32/T37 · Three tests that cannot fail, and the `ReadOnlyClient` underscore escape

> **Labels:** `test-integrity`, `audit:2026-08-30-01`
>
> **Body:**
>
> The suite is unusually strong and the author names this pattern five times, three
> self-cross-referenced — *"a test that can only observe the value the bug produces
> is not a test of it."* These are the ones that got away.
>
> - `tests/test_exceptions.py:27-31` constructs `CredentialsRejected("v2 client
>   rejected")` and asserts `"secret" not in repr(e)` — a property of a string the
>   test itself wrote. Cannot fail.
> - `tests/conftest.py:19` documents an opt-out marker
>   `@pytest.mark.expect_error_logs` that is **never implemented** and is
>   unregistered in `pyproject.toml:73`. The escape hatch is documentation only.
> - `scripts/check_docs.py` gates its own CI job and has **no tests**, unlike both
>   sibling guard scripts — which got test files precisely because untested guards
>   misfired in production.
>
> **And one hole in a control, not merely missing coverage:**
> `ReadOnlyClient.__getattr__` (`tests/integration/conftest.py:78-80`) passes any
> underscore-prefixed name straight through, so `live_client._backend.create_courses(...)`
> reaches the production organization. The guard is attribute-name-based only and
> no test probes the escape. **Fix this one first.**
>
> Also: `client.py` (462 lines) and `mcp/_schemas.py` (613 lines) have no test
> files at all.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

### 20 · T22 · Assert the externally-enforced controls

> **Labels:** `hardening`, `supply-chain`, `audit:2026-08-30-01`
>
> **Body:**
>
> The release pipeline is right, and is the sibling audit's worst finding designed
> against: `build` runs all project code and holds no `id-token`; `publish` holds
> `id-token: write` and contains only `download-artifact` +
> `pypa/gh-action-pypi-publish`, with no checkout and no install, and a comment
> saying so (`release.yml:8-15`, `:49-62`).
>
> The residual is that `environment: pypi` is only a control if that environment
> exists **with a required-reviewer rule** — GitHub creates a missing environment
> *unprotected* on first use, the rule lives in GitHub Settings, and the repository
> cannot verify it. The README states this. Same for branch protection, and for
> CodeQL, which `SECURITY-RESOURCES.md:222` discusses while no workflow file
> exists.
>
> **Fix:** a scheduled workflow asserting these against the GitHub and PyPI APIs,
> so an assumption becomes a check.
>
> Detail: [`FINDINGS.md` §4.8](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/FINDINGS.md)

---

## P4 — docs and tooling

### 21 · Adopt the audit's threat model as the living `THREAT_MODEL.md`

> **Labels:** `documentation`, `security`, `audit:2026-08-30-01`
>
> **Body:**
>
> Audit `2026-08-30-01` produced a 37-threat model across 20 entry points. It is
> committed inside the audit directory
> ([`THREAT_MODEL.md`](https://github.com/CloudSecurityAlliance/csa-skilljar/blob/main/docs/security-audits/2026-08-30-defending-code-reference-harness-claude/THREAT_MODEL.md))
> because an audit commits only its own directory.
>
> **What it contains:** the three control layers (Skilljar / MCP client / this
> server) with the first stated as an explicit assumption; the two-credential
> asymmetry as the model's centre of gravity; 37 threats sorted by impact ×
> likelihood with `controls` and `evidence` per row; 13 deprioritised threats with
> reasons; 15 class-level mitigations; and the open questions the code could not
> answer.
>
> **To adopt:** copy to the repository root, strip the frozen-snapshot banner, and
> rewrite the relative links. Decide whether `SECURITY.md` should link to it —
> `SECURITY.md` currently carries the threat framing inline and does not reference
> a separate model.
>
> **Note T1's conditional rating** — it depends on #1's outcome. If Skilljar
> sanitises, rescore before adopting rather than carrying the upper bound forward.

### 22 · Generate the audit index from front matter

> **Labels:** `tooling`, `audit:2026-08-30-01`
>
> **Body:**
>
> `docs/security-audits/README.md` is the one file every audit has to update — the
> index row and the coverage-by-module table. That makes it the single contention
> point in a workflow otherwise designed so parallel audit agents never share a
> file.
>
> The per-audit `README.md` front matter already carries everything the index
> needs: `audit_id`, dates, `tool`, `model`, `human_interaction`, `automation`,
> `review_depth`, finding counts, `remediation_status`, `scope_covered`.
>
> **Fix:** a script that walks `docs/security-audits/*/README.md`, parses front
> matter, and regenerates both tables. Run it in CI so a drifted index fails rather
> than misleads.
>
> Note `CloudSecurityAlliance/csa-google-workspace` has the same open issue against
> the same `SCHEMA.md`. Worth solving once and sharing — the two corpora
> deliberately use identical conventions.
