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

```bash
# Nothing to build yet. Planned:
pip install -e ".[dev]"
pytest -q                                    # offline: no network, no credentials
ruff check src tests && mypy
CSA_SKILLJAR_INTEGRATION=1 pytest tests/integration/   # real Skilljar, opt-in

# Available now — re-check upstream against the snapshots in specs/:
curl -s https://api.skilljar.com/v2/openapi.json | jq '.paths | keys | length'
curl -s https://api.skilljar.com/.well-known/oauth-authorization-server | jq -r '.scopes_supported[]'
```
