# Data Resources

Data assets this project owns, manages, or moves. Companion to `DATA-NEEDS.md`, which records what
the project still needs.

## Ecosystem overview

Two very different data stories, and keeping them apart is the point.

**In the repository:** public vendor API descriptions and analysis derived from them. Low
sensitivity, checked into git, safe to publish.

**In the running server:** learner PII in transit and nothing at rest. The server reads from
Skilljar and hands results to an MCP client in the same process lifetime. There is no cache, no
database and no log of content — a deliberate design constraint (design spec §2), not an
unimplemented feature.

```
Skilljar v1/v2  ──HTTPS──▶  csa-skilljar (in memory only)  ──stdio──▶  MCP client
                                    │
                                    └── nothing written to disk
```

## Asset: upstream OpenAPI snapshots

- **What it is** — Skilljar's published v1 (`schema.yml`, OpenAPI 3.0.3) and v2 (`openapi.json`,
  OpenAPI 3.1.0) documents, fetched 2026-08-26 and checked into `specs/`.
- **Classification** — `public`. Served without authentication from `api.skilljar.com`.
- **PII / GDPR** — no.
- **Deletion model** — `archival`. Snapshots are the baseline that drift detection compares
  against; superseded versions stay in git history.
- **Enrichment** — v1 is also stored as JSON for tooling parity with v2. No other transformation.
- **Destinations** — the repository (`public`); `scripts/check_upstream.py` reads them.
- **Why** — they are the contract the implementation is generated and tested against, and the
  baseline for detecting upstream change.
- **Technical detail** — `specs/skilljar-v1-openapi.{yml,json}`, `specs/skilljar-v2-openapi.json`.

## Asset: surface analysis

- **What it is** — a 66-entity reconciliation of both APIs, plus the live OAuth scope catalogue.
- **Classification** — `public`. Derived entirely from public documents.
- **PII / GDPR** — no.
- **Deletion model** — `explicit`. Regenerated when the snapshots change.
- **Enrichment** — entity mapping and field-level diffing across the two API generations; the
  interesting part, and the reason it is checked in rather than recomputed.
- **Destinations** — the repository (`public`).
- **Why** — it is the evidence behind the phase plan and the non-goals.
- **Technical detail** — `analysis/entity-inventory.{csv,json}`, `analysis/live-authz-metadata.json`.

## Asset: learner data (in transit only)

- **What it is** — names, email addresses, enrolment records, progress, quiz attempts, purchases.
  CSA's reference org holds 42,669 user records.
- **Classification** — `sensitive`. PII, GDPR-covered.
- **PII / GDPR** — **yes.** Skilljar is the system of record and the controller relationship sits
  with CSA, not with this tool. This project is a client and creates no new copy.
- **Deletion model** — `ephemeral`. Held in memory for the duration of a call. `anonymize_student`
  acts on Skilljar's copy and is irreversible there.
- **Enrichment** — none. Responses are passed through with shape normalisation only.
- **Destinations** — the calling MCP client, in-process. Never a file, never a log, never a
  third party.
- **Why** — enrolment management and progress reporting are core capabilities.
- **Technical detail** — no persistence layer exists. Domain objects need hand-written redacting
  `__repr__`s, because embedders log objects and a default dataclass dump is a data leak.

## Cross-system connections

| From | To | Carries | Sensitivity |
|---|---|---|---|
| `api.skilljar.com/v1` | server (memory) | learner records, content, commerce | sensitive |
| `api.skilljar.com/v2` | server (memory) | learner records, content, analytics | sensitive |
| server | MCP client (stdio) | tool results | sensitive |
| `api.skilljar.com` (specs, unauthenticated) | `specs/` | API descriptions | public |
| `specs/` | `analysis/` | derived inventory | public |

## Rules that must not erode

- **Never commit API response bodies.** Counts and shapes only — `.gitignore` covers the known
  patterns but the judgement call is the author's.
- **Redacting `__repr__` on anything holding learner data.** Never let `@dataclass` regenerate one.
- **No caching.** If a cache is ever proposed, it changes this file and the security posture, and
  it needs its own ADR.
