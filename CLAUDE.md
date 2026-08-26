# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this repository is

`csa-skilljar` — a Python library (import name `csa_skilljar`) and local stdio MCP server over
**both** Skilljar REST APIs. It reproduces the official Skilljar MCP server's 73-tool surface
exactly, then adds the capabilities that exist only in v1.

**Status: design complete, nothing implemented.** The repository holds the design spec, upstream
API snapshots, and surface analysis. Do not describe features as working; there is no `src/` yet.

## Where things live

- **`docs/superpowers/specs/2026-08-26-csa-skilljar-design.md`** — the authoritative design.
  Read it before proposing anything. Architecture, routing rule, credential model, error
  taxonomy, phasing, and three appendices of probe-verified facts.
- **`specs/`** — upstream OpenAPI snapshots, fetched 2026-08-26. `skilljar-v1-openapi.yml`
  (3.0.3, 160 paths / 340 ops) and `skilljar-v2-openapi.json` (3.1.0, 44 paths / 82 ops).
  These are *snapshots of someone else's moving target* — see "Upstream drift" below.
- **`analysis/`** — the 66-entity reconciliation of both APIs (`entity-inventory.csv`/`.json`),
  the live OAuth scope catalogue, and a browsable surface map.
- **`docs-html/`** — the rendered vendor doc pages, kept for provenance. Low value; the specs
  are the useful artifact.
- **`GOALS.md`** / **`BUSINESS-CASE.md`** — what success is, and the honest argument that this
  project should get smaller over time. Read before proposing scope changes.
- **`TODO.md`** — the index of ALL open work, per the CINO todo-index convention. Sweeping this
  plus open GitHub Issues finds everything. It also carries a consideration pile of things
  deliberately not committed to — check it before proposing a "missing" feature.
- **`DECISIONS-ADR.md`** + **`DECISIONS-ADR/`** — seven technical decisions with their rejected
  alternatives. ADR-002 (routing) and ADR-004 (no version in tool names) are load-bearing; do not
  contradict them without a superseding ADR.
- **`DECISIONS-PRD.md`** + **`DECISIONS-PRD/`** — scope, audience, and explicit out-of-scope.
- **`SECURITY-RESOURCES.md`** — exposure surface and the prompt-injection threat. Constrains any
  change that surfaces course content to a model.
- **`DATA-RESOURCES.md`** / **`DATA-NEEDS.md`** — what data is handled and what is deliberately
  never stored. **No caching, no persistence** — proposing either changes the security posture and
  needs its own ADR.
- **`WAITING-FOR.md`** + **`WAITING-FOR/`** — external conditions with observable triggers. 001 is
  the retirement trigger for each v1 family; 002 blocks all of Phase 1.
- **`FRICTION.md`** + **`FRICTION/`** — friction log. Low bar: if it is an annoyance for a human or
  an AI, log it.
- **`OPERATIONAL-RESOURCES.md`** — the one recurring job (`check_upstream.py`). Check its "Next
  review" date against today when working here.
- **`RACI.md`** — authority by domain. Note: **credential issuance is never delegated to AI.**
- **`CHATGPT.md`** / **`GEMINI.md`** — pointers to this file, deliberately not copies.

## Critical architectural facts

1. **The routing rule is absolute: v2 owns every capability v2 has; v1 is used only for
   capabilities v2 lacks.** No fallback, no dual-routing. Each capability has exactly one owner.
   This is what prevents silent degradation between two incompatible data models — v2 is JSON:API
   with cursor pagination, v1 is a flat DRF envelope. Do not add a fallback path.
2. **No version marker in any tool name, ever.** When Skilljar ships webhooks into v2 we change
   one backend and `list_event_subscriptions` keeps its name. A `v1_` prefix would force a rename
   that breaks every saved prompt.
3. **Enforcement is a wrapper around the backend seam, not a check in the tools.** `PolicyBackend`
   fails closed: a backend method with no declared gate is refused, not delegated. Library
   embedders get the same guarantee as MCP clients.
4. **Two independent credentials, both optional.** v1 is HTTP Basic (API key as username, empty
   password); v2 is OAuth `client_credentials`. Four states — both, v2 only, v1 only, neither —
   and none of them stop the server starting.
5. **We use `client_credentials`; the official server cannot.** `mcp.skilljar.com` advertises only
   `authorization_code`, because it is remote and acts for a browser user. Running locally removes
   the browser, the redirect URI, the consent flow and the token cache entirely.
6. **Parity is additive.** Identical tool and argument names to the official server, plus
   *optional* parameters where theirs is missing something (its `list_courses` has no pagination
   at all). A caller sending exactly what the official server accepts gets exactly what it
   returns.

## Invariants that fail silently — check these when editing

These come from `csa-google-workspace`, verified against `mcp` 2.1.0. Three of them fail with no
error at all. See
[PYTHON-SDK-TRAPS](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/research/mcp-servers/PYTHON-SDK-TRAPS.md).

1. **Nothing may touch stdout.** Under stdio, stdout *is* the JSON-RPC channel. One stray byte
   corrupts the session and the server looks alive while answering nothing. Every diagnostic goes
   to stderr. A test must assert no reachable configuration writes to stdout.
2. **Raise `ToolError`, never a plain exception.** Anything else becomes `UnexpectedToolError`
   with the message *discarded* — the user sees "Error executing tool X" and nothing more. One
   translation decorator at the tool boundary.
3. **Never use `Field(alias=…)` on a tool parameter.** It publishes a correct schema and then
   fails every call. A camelCase wire name must be the literal Python parameter name.
4. **`mcp.server.fastmcp` does not exist.** It is `from mcp.server import MCPServer`. This is the
   single most common thing a model writes confidently and wrongly. Pin `mcp>=2.1`.
5. **Sync tool handlers run on worker threads** (`anyio.to_thread.run_sync`). Any non-thread-safe
   client must be thread-local, never shared.
6. **`TypedDict` must come from `typing_extensions` below Python 3.12**, or pydantic silently
   emits no schema — tests pass on 3.12+, the 3.10 user sees nothing.
7. **Do not block `initialize` on a network call.** A slow or unreachable Skilljar becomes an
   opaque "server failed to start" with no way to say it was a credential problem. Startup checks
   are two tiers: synchronous config presence, then a background validity probe.

## Data hygiene — this repo touches real learner PII

The reference org has **42,669 users**. Probe output and API responses contain real names and
email addresses.

- **Never commit API response bodies.** Record counts and shapes, never rows. `.gitignore` covers
  the known patterns, but the judgement call is yours.
- **Never commit credentials.** `.env` is gitignored *in this repo*, not only in someone's global
  config — a public repo must not depend on a contributor's personal setup.
- **Redact in `__repr__`.** Domain objects holding learner data need hand-written reprs; embedders
  log these and the default dump is a data leak.
- **Never interpolate a credential into an error message.** Chain the cause, keep the message
  generic.

## Upstream drift — re-check before trusting this repo's map

Skilljar's v2 API is actively growing and the official MCP server tracks it. Everything in
`specs/` and `analysis/` is a snapshot from **2026-08-26**.

The vendor's own metadata runs ahead of the vendor's own API: the authorization server advertises
**88 scopes** while the published v2 spec uses **28**. Probing the 31 undocumented scope areas
returns `404` against a control that correctly distinguishes `401` (exists) from `404` (not
built) — so those scopes are a roadmap, and every gap this project fills is on it.

Practical rules:

- **Probe beats docs.** Vendor prose about this API has been wrong repeatedly during design —
  including a confident published claim that question banks were v1-only when v2 has full CRUD.
  If documentation and a probe disagree, the probe wins and the finding goes in the spec.
- **Re-check before claiming a gap.** The three commands are in `README.md`; automate them in
  `scripts/check_upstream.py`.
- **Be accurate and fair about Skilljar in public text.** They ship a good first-party server and
  are clearly investing in v2. This project complements it. Describe differences factually and
  without disparagement — this repo is public and CSA's name is on it.

## Operating rules — how to work here

These are not aspirations. Each one is here because it was violated during the design
session and cost something real.

1. **Inventory before declaring a blocker.** Before telling the user "I need X from you",
   look for X: `.env` in the working directory, environment variables, existing config,
   already-connected services. Phase 0 was declared blocked on a v1 API key that was
   sitting in this repo's own `.env` the whole time.

2. **Perishable access gets harvested, not sampled.** When a capability is human-gated,
   temporary, or about to be revoked, take *everything* on first contact rather than
   fetching what the current question needs. `FRICTION-001` records that enumerating the
   official MCP server needs an interactive login — that analysis was written, and then
   the registry was nearly lost anyway because nobody drew the conclusion. If access
   might not exist tomorrow, capture it completely today.

3. **Probe before asking.** If a question can be answered by a free, read-only,
   side-effect-free action, take the action instead of asking. Unauthenticated discovery
   documents, `401`-vs-`404` existence probes, and published spec files answered most of
   what was put to the user as a multiple-choice question.

4. **Convention completion.** When a documented convention determines a set of artifacts —
   the CINO project file set, the public-repo checklist — propose and produce the whole
   set rather than waiting to be asked for each piece.

5. **A check that cannot fail is theatre.** Every guard added here must be mutation-tested
   at least once: break the thing it guards, watch it fail, restore. `scripts/check_docs.py`
   was verified this way against both a wrong number and a reworded claim.

## Autonomy contract

**Proceed without asking:** read-only probes of anything; local file work; branches, PRs,
and merging documentation PRs on green; running tests; following a documented convention
to completion.

**Ask first:** anything that creates state on a third party (registering OAuth clients,
filing issues on other people's repos); publishing (PyPI, public repos); credential
issuance or scoping; destructive local operations; anything the spec lists as a non-goal.

## Working in this repo

- **Branch + PR for every change**; never commit to `main`. Conventional prefixes (`feat/`,
  `fix/`, `docs/`, `chore/`).
- **Plan then execute.** Write the spec or plan under `docs/superpowers/`, then implement TDD
  against `FakeBackend`. Keep `README.md` and `CHANGELOG.md` in sync.
- **Do not describe unimplemented things as working.** The README carries a status banner; keep it
  honest as phases land.
- Follows [CSA public repo standards](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/PUBLIC-GITHUB-REPO-STANDARDS.md):
  branch protection enforced for admins, required CI gates (lint, type-check, test matrix,
  coverage floor, security scan), Actions pinned to commit SHAs, releases via Trusted Publishing.

## Commands

**Always work inside a virtual environment.** Never `pip install` into a system or user
Python — for development, for CI, or for a user install. This is not a preference: the
machine this was built on had `mcp` **1.27.0** installed globally, which is the pre-2.0 API
where `mcp.server.fastmcp` still exists. Working outside a venv would have reproduced the
single most common MCP failure mode while the code looked correct.

```bash
python3 -m venv .venv                     # .python-version pins the interpreter (3.12)
.venv/bin/python -m pip install -e ".[dev]"

.venv/bin/python -m pytest -q             # offline: no network, no credentials
.venv/bin/ruff check src tests
.venv/bin/mypy
.venv/bin/python -m pytest -q --cov --cov-report=term-missing   # what CI's test job runs

# Real Skilljar, opt-in:
CSA_SKILLJAR_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/

# Documentation claims vs artifacts (also a required CI check):
.venv/bin/python scripts/check_docs.py
```

Do not run a bare `pytest` / `ruff` / `mypy` — they resolve to whatever is on `PATH`,
which is how a suite passes against the wrong dependency versions. Every command in this
file and in `README.md` is written `.venv/bin/...` for that reason.

**CI** pins the interpreter per matrix entry via `actions/setup-python`, which is the
same isolation by another mechanism. **Users** should install with `pipx install
csa-skilljar` (or `uv tool install`), which creates the venv for them — a plain
`pip install` into a system Python is the one path we do not support.

## Re-check upstream against the snapshots in `specs/`

```bash
curl -s https://api.skilljar.com/v2/openapi.json | jq '.paths | keys | length'
curl -s https://api.skilljar.com/.well-known/oauth-authorization-server | jq -r '.scopes_supported[]'
```
