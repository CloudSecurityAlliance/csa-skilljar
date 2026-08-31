# Security audit records

One directory per audit. Each records what was examined, by what, under what
conditions, and what was found — including what was looked for and *not* found,
and what was rescored or withdrawn along the way.

The **living** documents are elsewhere and are what to read first:

- [`SECURITY.md`](../../SECURITY.md) — the standing threat framing, and the
  division of responsibility between this project, the operator, and Skilljar.
- `THREAT_MODEL.md` at the repository root — the current threat model, once
  adopted. Each audit directory keeps the model as that audit produced it; an
  audit **proposes** the living model by filing an issue rather than editing a
  root file, so parallel audits cannot collide over it. The 2026-08-30 audit's
  model is [here](2026-08-30-defending-code-reference-harness-claude/THREAT_MODEL.md).

Structure, naming, front-matter schema and conventions: [`SCHEMA.md`](SCHEMA.md).
That file is kept **byte-identical in intent** with the copy in
`CloudSecurityAlliance/csa-google-workspace`, so a reader who knows one corpus
knows the other.

---

## Index

Newest first.

| audit | date | tool | model | interaction | automation | depth | findings | remediation |
|---|---|---|---|---|---|---|---|---|
| [2026-08-30 · defending-code-reference-harness / claude](2026-08-30-defending-code-reference-harness-claude/) | 2026-08-30 → 08-31 | claude-code + anthropics/defending-code-reference-harness | claude-opus-5 | heavy | assisted | adversarial | 37 threats · 2 flaws · 1 conditional · 13 hardening | deferred by design |

---

## Coverage and staleness

The most useful thing this index can tell you is **which audit covered which
code**. Record it here when adding an audit; a record whose coverage is not
written down will later be mistaken for broader than it was.

| module group | first covered by |
|---|---|
| `src/csa_skilljar/` — `backend.py`, `v1backend.py`, `client.py`, `auth.py`, `scopes.py`, `policy.py`, `exceptions.py` | **2026-08-30 · claude** |
| `src/csa_skilljar/mcp/` — server, cli, `_config.py`, `_schemas.py`, and all 23 tool families (112 tools) | **2026-08-30 · claude** |
| `tests/` **as code**, including `tests/integration/` and the read-only guard | **2026-08-30 · claude** |
| `.github/workflows/`, `.githooks/`, `scripts/`, packaging, secret hygiene | **2026-08-30 · claude** |
| `docs/`, `DECISIONS-ADR/`, `DECISIONS-PRD/`, `FRICTION/`, `analysis/` | **2026-08-30 · claude** |
| Skilljar's own rendering of `content_html` | **not covered — requires empirical testing, see T1** |
| Any write path against a real Skilljar organization | **never executed, by the project's own record** |

## What an audit may commit

**An audit commits only its own directory.** Nothing else — not `SECURITY.md`,
not a root `THREAT_MODEL.md`, not a stale `CLAUDE.md` it noticed in passing, and
not a source fix however small. Everything outside the audit directory is
written up and **filed as an issue**.

Two reasons, and the second is the load-bearing one:

1. It keeps the flaw trail and the fix trail separate, so both stay
   independently reviewable.
2. **It lets audits run in parallel.** Several audit agents can work the same
   commit at once — different tools, different scopes — and never touch a shared
   file. That property disappears the moment an audit may edit a document
   outside its own directory.

The one exception is this index and `SCHEMA.md`. That is the known contention
point, and the fix is to generate the index from the per-audit front matter.

## Auditing the same commit with a different tool

Encouraged, and the reason the tool name is in the directory name. Two audits of
`280c8e8` by different tools are directly comparable, and the interesting output
is the disagreement: what one found and the other missed, and where they rated
the same finding differently.

The cheapest thing a second audit can inherit is the previous one's
**investigated-and-cleared** list — §7 of the 2026-08-30 record clears thirteen
items with reasons, including the absence of any local filesystem write, the
non-applicability of every `mcp`-SDK transport advisory to a stdio-only server,
the refuted unverified-JWT concern, and the confirmed absence of learner PII in
test fixtures. Its §6 records where two of that audit's own agents disagreed and
how it was resolved, plus one arithmetic error the orchestrator made and
corrected — both of which are the calibration a comparing reader needs.
