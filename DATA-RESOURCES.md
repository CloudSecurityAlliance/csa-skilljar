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

## Asset: demonstration and test transcripts

- **What it is** — the conversation log produced when someone runs a demo, a tour, or a
  manual check through an MCP client. It contains whatever the tools returned.
- **Classification** — `sensitive` if it touched learner data, `internal` otherwise.
- **PII / GDPR** — **potentially yes, and this is the one place the design's "nothing at rest"
  promise does not hold.** Everything above is ephemeral because the server writes nothing. A
  transcript is different: it is written by the *client*, it persists, it gets scrolled back,
  pasted into a ticket, quoted in a pull request, and screenshotted into a slide. A demo is
  therefore a **new destination for PII that the rest of this document does not cover.**
- **Deletion model** — outside this project's control, which is exactly why the constraint below
  is on the input rather than the output.

### Demonstrations run against named accounts only

**Decided 2026-08-27.** Any demo, tour, or manual walkthrough reads learner data for
**`@cloudsecurityalliance.org` addresses and `kurt@seifried.org`** — nobody else. Never an
unfiltered listing.

The reference organization holds **42,669 real learners**. `list_students()` with no filter
returns strangers' names and email addresses into a transcript that will outlive the demo, for
no benefit: a tour proves the tools work, and it proves that just as well against five accounts
as against forty thousand.

**Skilljar cannot filter by domain, so this has to be done deliberately.** `filter[email]` is an
**exact, case-insensitive match** — there is no `contains`, no `endswith`, no domain filter.
"Everyone at cloudsecurityalliance.org" is not a question the API can answer, so a demo cannot
narrow a broad listing after the fact. It must start from specific addresses.

The workable pattern, given what the API actually offers:

1. Resolve each named address once — `list_students(filter_email="someone@cloudsecurityalliance.org")`.
2. Scope every learner-facing read by the resulting id. Each of these takes a student filter,
   so no broad listing is needed at any point:

   | Tool | Filter to use |
   |---|---|
   | `list_enrollments` | `filter_student_email` (takes the address directly) |
   | `list_certificates` | `filter_student_id` |
   | `list_course_ratings` | `filter_student_id` |
   | `list_signup_field_values` | `filter_student_id` |

3. Content tools — courses, lessons, quizzes, question banks, domains, published courses — carry
   no learner PII and need no restriction.

**Two specific hazards.** `list_course_ratings` returns learner-written free text and is **not
paginated**, so an unscoped call returns every rating a course ever received in one response.
`list_signup_field_values` returns whatever learners typed into registration fields, which is
frequently employer and job title.

When `demonstration_plan` is built it should carry this allowlist as a default, name the accounts
it will touch before it touches them, and refuse to widen silently.

## Cross-system connections

| From | To | Carries | Sensitivity |
|---|---|---|---|
| `api.skilljar.com/v1` | server (memory) | learner records, content, commerce | sensitive |
| `api.skilljar.com/v2` | server (memory) | learner records, content, analytics | sensitive |
| server | MCP client (stdio) | tool results | sensitive |
| MCP client | transcript (persisted by the client) | whatever was returned | sensitive — the one path that outlives the process |
| `get_asset` result | anyone who reads the URL | **the course file itself**, for ~60 minutes, with no credentials | sensitive — a bearer capability, not a reference |
| `api.skilljar.com` (specs, unauthenticated) | `specs/` | API descriptions | public |
| `specs/` | `analysis/` | derived inventory | public |

## Rules that must not erode

- **Never commit API response bodies.** Counts and shapes only — `.gitignore` covers the known
  patterns but the judgement call is the author's.
- **Redacting `__repr__` on anything holding learner data.** Never let `@dataclass` regenerate one.
- **No caching.** If a cache is ever proposed, it changes this file and the security posture, and
  it needs its own ADR.
- **A `download_url` is the file, not a pointer to it.** Presigned, credential-free, valid
  about an hour. Do not paste one anywhere it will outlive the task, and do not store it —
  it expires and then reads as a broken asset rather than an expired link.
- **Demos read named accounts only** — `@cloudsecurityalliance.org` and `kurt@seifried.org`. A
  transcript persists, so an unfiltered `list_students()` puts strangers' PII somewhere this
  project cannot delete it from.
