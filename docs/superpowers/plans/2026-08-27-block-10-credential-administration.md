# Block 10 — Credential administration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** The eight v2 operations the official server omits — everything that audits, rotates,
constrains or revokes an OAuth credential.

**Architecture:** First block past parity. All eight sit behind `admin.credentials`, off in every
profile but `admin`, matching `register_oauth_client` from Block 9.

**Spec:** v2 OpenAPI `specs/skilljar-v2-openapi.json` · [design spec](../specs/2026-08-26-csa-skilljar-design.md)

## Global Constraints

Unchanged from Blocks 2–9.

---

## Why this block exists

Skilljar's official MCP server exposes `register_oauth_client` — the tool that **mints** a
credential — and withholds every tool that **audits or remediates** one. You can create an OAuth
client through it and then cannot list what exists, see what a client may do, narrow it, rotate a
leaked secret, or turn it off.

That is the asymmetry this block closes. It is also why all eight are `admin`-gated: a tool that
can enumerate and rotate every credential in an organization is not something to have on by
default, and `RACI.md` keeps credential issuance out of what AI decides alone.

## The tools

| Tool | Operation | Scope |
|---|---|---|
| `list_oauth_clients` | `GET /v2/clients/` | `clients:read` |
| `get_oauth_client` | `GET /v2/clients/{id}` | `clients:read` |
| `create_oauth_client` | `POST /v2/clients/` | `clients:write` |
| `update_oauth_client` | `PATCH /v2/clients/{id}` | `clients:write` |
| `deactivate_oauth_client` | `DELETE /v2/clients/{id}` | `clients:write` |
| `rotate_oauth_client_secret` | `POST /v2/clients/{id}/rotate-secret` | `clients:write` |
| `list_oauth_scopes` | `GET /v2/scopes/` | `clients:read` |
| `revoke_refresh_token` | `POST /v2/auth/revoke` | **none** |

## The traps

| # | Trap | Fails how | Pinned by |
|---|---|---|---|
| 1 | **Two ways to create a client**, and one produces something that cannot read anything | Silently — the DCR client authenticates fine and returns empty results forever | `test_the_two_creation_paths_are_disambiguated` |
| 2 | `revoke_refresh_token` returns **200 for a token that never existed** (RFC 7009 §2.2) | **Silently.** A typo'd token reports "revoked" | `test_revoke_says_success_is_not_evidence` |
| 3 | `revoke` is **unauthenticated** — the second such call | Would leak our bearer token to an endpoint that does not want it | `test_revoke_never_sends_our_bearer_token` |
| 4 | `DELETE /v2/clients/{id}` is **"Deactivate client"**, not a delete | A model reports deletion; the row survives | `test_deactivate_is_not_described_as_deletion` |
| 5 | `create` and `rotate` return a **one-time secret**, never retrievable | Lost forever if not stored | both descriptions + `warning` field |
| 6 | Rotating invalidates the old secret **immediately** | Everything using it breaks, with no warning from anywhere else | `test_rotate_warns_the_old_secret_dies_immediately` |
| 7 | `scope_codenames` and `scope_preset` are two ways to say the same thing | Sending both is ambiguous | validation rejects both together |

### Probe findings behind traps 2 and 3

`POST /v2/auth/revoke`, verified 2026-08-27 against live Skilljar with a deliberately invalid
token:

```
no Authorization header, token="not-a-real-token-000"  ->  200, empty body
with Authorization,      token="not-a-real-token-000"  ->  200, empty body
```

So it is unauthenticated, and a 200 says nothing about whether anything was revoked. RFC 7009
specifies exactly this, to stop the endpoint being used to test whether a token is valid.

`GET /v2/scopes/` with a token lacking `clients:read` returns `403 permission_denied`, which is
what the local scope pre-check exists to save.

## Files

- Create: `src/csa_skilljar/mcp/_tools/credentials.py`, `tests/test_credentials.py`
- Modify: `backend.py` (Protocol/Fake/V2 × 8), `client.py`, `_schemas.py`, `policy.py`,
  `server.py`, `_tools/__init__.py`
- Modify: `tests/test_protocol.py`, `test_policy.py`, `test_descriptions.py`, `test_pagination.py`
- Modify: `tests/test_web_packages.py` — the "only one unauthenticated path" guard must now
  expect two, and say which
- Modify: `README.md` (→ 84 tools), `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`

## Task sequence

- [ ] **Task 1 — Reads.** `list_oauth_clients`, `get_oauth_client`, `list_oauth_scopes`.
- [ ] **Task 2 — Create and update.** Traps 1, 5, 7.
- [ ] **Task 3 — Rotate and deactivate.** Traps 4, 5, 6.
- [ ] **Task 4 — Revoke.** Traps 2 and 3, and generalising the unauthenticated-path guard.
- [ ] **Task 5 — Mutations, docs, PR.**

## Mutations required before the PR

| Mutation | Must be killed by |
|---|---|
| `revoke` routed through `_send` | `test_revoke_never_sends_our_bearer_token` |
| Any client tool gated below `admin.credentials` | policy matrix + per-profile refusal |
| `revoke` described as confirming revocation | `test_revoke_says_success_is_not_evidence` |
| `deactivate` described as deletion | `test_deactivate_is_not_described_as_deletion` |

**Ships:** v0.9.0.
