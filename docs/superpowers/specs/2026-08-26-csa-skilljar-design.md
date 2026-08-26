# csa-skilljar — design

**Status:** approved design, pre-implementation
**Date:** 2026-08-26
**Supersedes:** nothing (new project)

A Python library and local stdio MCP server covering **both** of Skilljar's REST APIs. It
reproduces the official Skilljar MCP server's tool surface exactly, then adds the capabilities
that exist only in the v1 API.

---

## 1. Why this exists

Skilljar ships an official MCP server at `https://mcp.skilljar.com/mcp`. It is built on the v2
API and exposes **73 tools**, verified by connecting to it and enumerating the registry. Those 73
tools are a close mechanical mapping of v2's 82 operations — 57 of them are plain
`list_`/`get_`/`create_`/`update_`/`delete_` CRUD, and there are no composite or task-shaped
tools.

The v1 API remains far larger (340 operations against v2's 82) and holds capabilities v2 does not
have: webhooks, learner progress, learning paths, asset upload, instructor-led training, and the
commerce stack. None of it is reachable from any MCP client today.

This project closes that gap without asking anyone to choose. Its four differentiators:

1. **One tool surface over both APIs.** Which API serves a tool is an implementation detail.
2. **Local stdio.** Credentials stay on the operator's machine.
3. **Capability gating.** An install exposes a profile, not the whole surface.
4. **The library is the product too.** CSA's content pipeline needs scriptable Python, not only
   agent tools.

### 1.1 The shelf life is real, and deliberate

`api.skilljar.com/.well-known/oauth-authorization-server` advertises **88 OAuth scopes** while the
published v2 spec uses **28**. Probing all 31 undocumented scope areas returns `404` against a
control that correctly separates `401` (exists, needs auth) from `404` (not built) — so the
scopes are a published roadmap, and every gap this project fills is on it.

That is not a reason to skip the work: the endpoints do not exist yet, v1 keeps working, and a
capability moving from v1 to v2 changes one backend rather than any tool name. It *is* a reason
to detect drift automatically rather than to assume this document stays true. See §9.

---

## 2. Non-goals

Stated explicitly so they are decisions rather than omissions.

- **No webhook receiving.** We manage subscriptions; we are not an HTTP endpoint.
- **No caching layer.** Accessors re-fetch. Sessions are live and multi-actor.
- **No cross-API composite writes.** v2 has a batch envelope with per-item results; v1 has
  nothing equivalent. Multi-step writes stay the caller's business.
- **No catalog page-building.** ~60 v1 operations for a page builder an agent should not drive.
- **No v1 families with no data in the reference org:** license packages, progress tokens,
  multi-session events, access-code pools (see Appendix A).
- **No attempt to keep working through upstream change.** We detect drift and report it.

---

## 3. Architecture

The shape follows `csa-google-workspace`: a library that is the product, with the MCP server as a
thin delivery layer over it.

```
                  MCP client (stdio, JSON-RPC over stdout)
                                  |
                    mcp/server.py  create_server(get_client)
                    per-family register_*_tools producers
                                  |
                          PolicyBackend(backend, policy)     <- one enforcement seam
                                  |
                        SkilljarClient  (the library)
                                  |
                 +----------------+----------------+
                 |                                 |
            V2Backend                          V1Backend
       OAuth client_credentials            HTTP Basic, key as user
       JSON:API, cursor, batch             DRF envelope, cursor + count
```

### 3.1 Routing rule

**v2 owns every capability v2 has. v1 is used only for capabilities v2 lacks.**

There is no fallback and no dual-routing. Each capability has exactly one owner, which means:

- no silent degradation between two different data models,
- no tool-name collisions,
- migration is a one-line backend change when a capability lands in v2.

### 3.2 The backend seam

`Backend` is a protocol. Three implementations:

- `V2Backend` — the v2 API.
- `V1Backend` — the v1 API.
- `FakeBackend` — in-memory, powers the entire offline unit suite.

A conformance test reflects over the protocol and asserts all three satisfy the same signatures,
so a method added to one but not the others fails CI rather than leaving the suite exercising a
stale double.

### 3.3 Enforcement

`PolicyBackend` wraps the seam, not the tools — so a library embedder gets the same guarantee as
an MCP client. It **fails closed**: a backend method with no declared gate is refused, not
delegated, so a new capability arrives *off*.

---

## 4. Tool surface

### 4.1 Naming principles

1. **No version marker in any tool name, ever.** When Skilljar ships webhooks into v2 we swap the
   backend and `list_event_subscriptions` keeps its name. A `v1_` prefix would force a rename
   that breaks every saved prompt.
2. **Name the job, not the endpoint.** v1's ten `/v1/webhooks/sample-*` endpoints become one
   `preview_event_payload(event_type)`.
3. **Match the official verb conventions across the seam** — `list_`/`get_`/`create_`/`update_`/
   `delete_`, plural for batch. Consistency matters more than elegance in the new half.
4. **Compose reads, never writes.** A read tool issuing three GETs is a convenience. A write tool
   issuing three POSTs is a partial-failure trap.

### 4.2 Additive compatibility

Phase 1 reproduces all 73 official tool names **and their argument names** exactly. Where the
official tool is missing something, we add *optional* parameters that default to its behavior.

The worked example: official `list_courses` accepts only `filter.title` — no pagination at all.
Ours accepts `filter.title` plus optional `page.cursor` and `page.size`. A caller sending exactly
what the official server accepts gets exactly what it returns.

Parity is **tested, not claimed**: a stored snapshot of the official registry is diffed in CI, and
drift opens an issue.

### 4.3 Tool descriptions are a first-class deliverable

The official descriptions are accurate and thin. `list_courses` reads *"List non-deleted,
non-draft courses for the authenticated organization"* — true, and it does not tell a model that
there is no pagination parameter or that a large catalog will truncate silently.

Every tool description here must state: what it returns, what it will not return, which argument
is required and why, and what the caller should do next. This is the difference between an
intelligent server and a wrapper, and it is what the demonstration (§8.3) actually tests.

### 4.4 Phases

| Phase | Content | Tools |
|---|---|---|
| 0 | Verify v1 is live — **done**, see Appendix A | — |
| 1 | Parity: the 73 official tools, v2 only | 73 |
| 2 | Remaining v2: credential administration, `admin` profile, off by default | ~8 |
| 3 | Learner progress | ~4 |
| 4 | Assets & media | ~5 |
| 5 | Commerce, read-biased | ~8 |
| 6 | Learning paths | ~6 |
| 7 | Events & webhooks | ~6 |
| 8 | vILT / ILT | ~6 |
| 9 | Labels & tags | ~4 |

Roughly 120 tools exist; a profile registers a working subset.

Phase 2 needs care. Skilljar exposes `register_oauth_client` — which mints a credential — while
withholding `list_clients` and `rotate_secret`, which audit and remediate. Adding the rest hands
an agent full credential administration, so it is off unless an operator names the `admin`
profile.

---

## 5. Credentials

### 5.1 Two independent credentials, both optional

| | v1 | v2 |
|---|---|---|
| Mechanism | HTTP Basic, API key as username, empty password | OAuth 2.0 `client_credentials` |
| Config | `CSA_CSA_SKILLJAR_V1_API_KEY` | `CSA_SKILLJAR_V2_CLIENT_ID` / `CSA_SKILLJAR_V2_CLIENT_SECRET` |
| Cached state | none | short-lived access token, in memory only |

**We use `client_credentials`, which the official MCP server cannot.** `mcp.skilljar.com`
advertises only `authorization_code` + `refresh_token` because it is remote and acts for a browser
user. Running locally, we take a client id and secret straight to `/v2/auth/token` — no browser,
no redirect URI, no consent flow, no `login` subcommand, no token file. That removes an entire
subsystem `csa-google-workspace` needed.

Four states, none of which stop the server: both credentials, v2 only, v1 only, neither. In the
last case the server still starts and every tool returns setup instructions — a first-time user's
first experience is a tool error, so that error **is** the onboarding document.

### 5.2 Startup is two tiers

The server must never block `initialize` on a network call. If Skilljar is slow the handshake
times out and the client reports an opaque "server failed to start", with no way to say it was a
credential problem.

- **Tier 1 — synchronous, no network.** Is the variable set? Is the cached JWT already expired
  (readable locally from `exp`)? Written to **stderr**, and shapes the `INSTRUCTIONS` string.
- **Tier 2 — background, after `initialize` returns.** One cheap call per credential. The verdict
  is cached and read by `check_access` and by tool errors.

Nothing may touch **stdout**: under stdio it *is* the JSON-RPC channel. A test must assert that no
reachable configuration puts bytes on it.

### 5.3 Auth error taxonomy

Seven states, each with exactly one remedy. Anything unclassifiable gets the generic form rather
than a guess.

| # | State | Detected by | Behavior |
|---|---|---|---|
| 1 | v1 key absent | config, startup | Remedy + "v2 tools still work" |
| 2 | v1 key rejected | `401` | "Rotated or revoked" + reissue steps |
| 3 | v1 key lacks permission | `403` | Names the operation; org-admin action |
| 4 | v2 credentials absent | config, startup | Remedy + "v1 tools still work" |
| 5 | v2 token expired | JWT `exp`, local | **Silent.** Re-grant and retry once. Not an error. |
| 6 | v2 client rejected | `401` on token grant | "Secret rotated or client deleted" + reissue |
| 7 | v2 token lacks scope | pre-checked locally | Names the exact missing scope |

Every message states **why this tool** needs the missing credential, **what still works**, and the
concrete next step. None ever echoes any part of a credential.

We link Skilljar's own documentation for obtaining credentials rather than transcribing dashboard
navigation, which we cannot verify and which would rot.

### 5.4 Local scope pre-check

v2 declares `x-required-scope` on every operation and the granted scopes are readable from the
token. So each tool's required scope is **baked into its metadata at build time from the spec**,
and checked locally before any call:

```
`create_question_banks` needs the `question-banks:write` scope.
Your v2 client was issued: courses:read, courses:write, lessons:read, lessons:write.

Re-issue the client including `question-banks:write`, then restart the server.
No call was made to Skilljar.
```

Precise, actionable, and produced with zero network traffic.

---

## 6. Capability gating and profiles

Two layers, doing different jobs:

- **Profile controls registration.** An unregistered tool costs no context. This is the answer to
  ~120 tools.
- **`PolicyBackend` controls execution.** Defense in depth, and the guarantee library embedders
  get.

Profiles: `parity` (the 73 v2 tools — the default), `authoring`, `people`, `reporting`,
`operations`, `admin`, `full`. Composable. The configuration is the complete permitted list, not a
delta, and **cannot be widened in-band** — no tool changes it.

**One tool is always registered: `describe_capabilities`.** Without it, a tool the model cannot
see becomes a capability the user never learns exists — the model says "this server doesn't
support webhooks" when the truth is one profile change away. It reports what exists but is not
enabled, for about 100 tokens.

---

## 7. Error model

The library raises a typed hierarchy. One decorator at the tool boundary translates it.

Every user-facing failure must be raised as the SDK's `ToolError`. Anything else becomes
`UnexpectedToolError` **with the message discarded**, so the user sees "Error executing tool X"
and nothing about what went wrong. This has bitten `csa-google-workspace` repeatedly and is the
single highest-value rule in the delivery layer.

---

## 8. Testing

### 8.1 Three tiers

- **Unit** — offline, `FakeBackend`, gates CI. The whole surface must be testable with no network
  and no credentials.
- **Integration** — real Skilljar, opt-in behind `CSA_SKILLJAR_INTEGRATION=1`.
- **Conformance** — asserts `FakeBackend`, `V1Backend` and `V2Backend` satisfy one protocol.

### 8.2 The fake/real blind spot

A fake that powers every unit test can be more permissive than reality and hide a real bug.
Behavior only a real backend has — pagination, error translation, the `GET /v1/lessons` 400 —
needs a stub-service test, not a fake test.

### 8.3 The demonstration is the end-to-end test

Per the proven pattern: the in-session tool returns **the plan**, not the result, and the model
calls the real tools. That tests whether the tool descriptions are usable from a standing start,
which is the actual product (§4.3). Coverage is computed from the tool registry, so a new tool
appears as a gap rather than being quietly absent.

### 8.4 Gate expectations are hand-written

The capability expectation map is written out by hand, never derived from the gate table.
Deriving it tests the table against itself and passes no matter what it says.

---

## 9. Upstream drift detection

`scripts/check_upstream.py` compares live upstream against the snapshots in `specs/` and reports:

1. v2 operation count and path set, from `https://api.skilljar.com/v2/openapi.json`
2. the advertised scope catalog, from the authorization-server metadata
3. the official MCP server's tool registry, when credentials are present

It runs weekly in CI and opens an issue on drift. This is a **script, not reference prose**,
because it is deterministic and prose about a moving target is wrong by default.

---

## 10. Research questions

CINO-Platform-Engineering's MCP research notes that the gap to a `mcp-server-development` skill is
breadth: everything proven so far comes from exactly two servers. This is the **third**, and a
different shape again — two upstream APIs, two credential mechanisms, no user-data custody, and a
vendor actively moving underneath it.

Questions it should answer:

1. Does the single-`PolicyBackend` pattern hold when the seam fronts **two** backends?
2. Is profile-controlled registration a sound context-cost control, or does hiding tools cost more
   in confusion than it saves in tokens?
3. Does "the demo is the end-to-end test" survive a server where a whole half may be unavailable
   for credential reasons?
4. Is a build-time scope pre-check from the OpenAPI spec generalizable to other scoped APIs?
5. What is the right cadence for upstream drift detection against a vendor shipping quarterly?

---

## Appendix A — Phase 0 findings (verified 2026-08-26)

Live GETs against the CSA production org using a read-only key. Every family returned `200`.

| Family | Rows | Family | Rows |
|---|---|---|---|
| users | 42,669 | web-packages | 533 |
| promo-codes | 13,687 | offers | 376 |
| promo-code-pools | 4,278 | vilt-session-registrations | 341 |
| assets | 157 | groups | 134 |
| vilt-session-events | 103 | published-courses (main domain) | 65 |
| labels | 50 | tags | 17 |
| course-series | 14 | published-paths | 10 |
| ilt-instructors | 9 | catalog-pages | 9 |
| webhooks | 3 | question-banks | 1 |

**Empty in this org:** license-packages, progresstokens, ilt-multi-session-events,
access-code-pools. All four are non-goals (§2).

**Two quirks that shape tool design:**

- `GET /v1/lessons` returns `400 {"query_params": "Course ID required as a query parameter"}`.
  Lessons cannot be enumerated org-wide on v1; `course_id` is required, and the description must
  say so or a model will call it bare.
- v1 pagination is **cursor-based and also returns a total `count`**
  (`next=...?cursor=cD02MzgyMDg%3D&page_size=2`). v2 is cursor-based with **no** total. On this
  one axis v1 is better: it can report scale before iterating.

## Appendix B — the official tool registry (73, verified 2026-08-26)

```
add_group_memberships          add_visibility_overrides      anonymize_student
bind_quiz_question_banks       bulk_enroll_students          complete_enrollments
create_courses                 create_groups                 create_lessons
create_question_banks          create_questions              create_quizzes
create_signup_field_values     create_students               create_web_packages
deactivate_student             delete_groups                 delete_published_course
delete_question_banks          delete_questions              delete_quizzes
delete_web_package             get_certificate               get_course
get_course_analytics           get_domain                    get_enrollment
get_group                      get_lesson                    get_published_course
get_question                   get_question_bank             get_quiz
get_signup_field_value         get_student                   get_web_package
list_certificates              list_course_ratings           list_courses
list_domains                   list_enrollments              list_groups
list_lessons                   list_published_courses        list_question_banks
list_questions                 list_quiz_question_bank_assignments
list_quizzes                   list_signup_field_values      list_students
list_visibility_overrides      list_web_packages             publish_courses
register_oauth_client          remove_group_memberships      remove_visibility_overrides
republish_published_course     send_password_reset           set_student_password
unbind_quiz_question_banks     unpublish_published_course    update_courses
update_enrollments             update_groups                 update_lessons
update_published_courses       update_question_banks         update_questions
update_quiz_question_banks     update_quizzes                update_signup_field_values
update_students                update_web_packages
```

Not exposed by the official server: `GET /v2/scopes/`, the six `/v2/clients/` operations, and
`POST /v2/auth/{token,revoke}`.

## Appendix C — verified upstream facts

Everything below was confirmed by probe on 2026-08-26, not read from vendor prose. Several
published claims about this API proved wrong during design; treat undocumented assertions with
suspicion and re-probe.

| Fact | Evidence |
|---|---|
| v1 spec | `https://api.skilljar.com/docs/schema.yml` — OpenAPI 3.0.3, 160 paths / 340 ops |
| v2 spec | `https://api.skilljar.com/v2/openapi.json` — OpenAPI 3.1.0, 44 paths / 82 ops |
| v2 docs URL | `https://api.skilljar.com/v2/docs` — **no trailing slash**; `/v2/docs/` 404s |
| Official MCP | `https://mcp.skilljar.com/mcp`, 73 tools, OAuth-gated |
| MCP grants | `authorization_code`, `refresh_token` only — **no** `client_credentials` |
| API grants | `client_credentials` at `https://api.skilljar.com/v2/auth/token` |
| Scope catalog | 88 advertised; 28 used by the published spec |
| Roadmap areas | 31 scope areas with no endpoints — all return `404` against a `401`/`404` control |
| Question banks | Full CRUD in **both** APIs; v1 cannot add a question to a bank or bind a bank to a quiz |
| v2 timestamps | `created_at`/`modified_at` everywhere **except** `GroupAttributes`, which uses `updated_at` |
