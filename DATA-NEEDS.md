# Data Needs

What this project needs to advance and to sustain. Companion to `DATA-RESOURCES.md`, which records
what it already has.

## Advance

| What | Why | Source | Freshness | Priority | Status | Fulfilled by |
|---|---|---|---|---|---|---|
| v2 OpenAPI document | Generates tool signatures and the per-operation required-scope table baked into tool metadata | `api.skilljar.com/v2/openapi.json` | weekly | critical | fulfilled | `specs/skilljar-v2-openapi.json` |
| v1 OpenAPI document | Same, for the v1-only families | `api.skilljar.com/docs/schema.yml` | weekly | critical | fulfilled | `specs/skilljar-v1-openapi.yml` |
| Official MCP tool registry | The parity baseline (ADR-006) — 73 names and their argument names | live `tools/list` against `mcp.skilljar.com` | on change | critical | **partial** | Enumerated once, 2026-08-26. Needs snapshotting into `specs/`. See `FRICTION-001`. |
| v2 OAuth client credentials | Nothing in Phase 1 can be built or tested without one | Skilljar Dashboard | one-time | critical | **blocked** | `WAITING-FOR-002` |
| Reference-org usage volumes | Set the phase order and justified cutting four families | live v1 read-only probe | one-time | high | fulfilled | Design spec Appendix A |

## Sustain

| What | Why | Source | Freshness | Priority | Status | Fulfilled by |
|---|---|---|---|---|---|---|
| v2 endpoint availability per reserved scope | The retirement trigger — when v2 ships a capability, the v1 family behind it is retired | `401`-vs-`404` probe per area | weekly | high | planned | `scripts/check_upstream.py`, `WAITING-FOR-001` |
| OAuth scope catalogue | Leading indicator of upcoming v2 capability, ahead of any endpoint | `api.skilljar.com/.well-known/oauth-authorization-server` | weekly | medium | planned | `scripts/check_upstream.py` |
| Official registry drift | Parity is a claim about software that changes without us | live `tools/list` | weekly, credentials permitting | medium | planned | `scripts/check_upstream.py` |

## Notes

Every need here is **API description data**, not content data. The project needs no training
corpus, no dataset acquisition and no third-party feed — it needs an accurate picture of a moving
vendor API, which is why the sustain half is a script rather than a documented habit.

The one need that is *not* mechanically fulfillable is the official tool registry: reading it
requires an interactive OAuth login (`FRICTION-001`). Until that is resolved, the drift check
degrades gracefully — it reports the two unauthenticated signals and notes that the registry check
was skipped, rather than silently passing.
