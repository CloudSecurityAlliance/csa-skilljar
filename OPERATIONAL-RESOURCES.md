# Operational Resources

Recurring operational work. This project deploys no service and runs no infrastructure — it is a
library and a local process on the user's machine — so there is exactly one entry, and it is about
watching someone else's API rather than running our own.

## check_upstream — Skilljar API drift detection

- **What it does** — Compares live Skilljar upstream against the snapshots in `specs/` and reports
  what moved: the v2 operation set, the advertised OAuth scope catalogue, per-area endpoint
  availability (`401` vs `404`), and the official MCP server's tool registry when credentials
  allow. Opens a GitHub issue on drift.
- **Tier** — `simple-scheduled`
- **Status** — `production`
- **Code** — `scripts/check_upstream.py`; workflow `.github/workflows/upstream.yml`
- **Runtime** — Python, GitHub Actions
- **Schedule** — weekly, plus manual dispatch
- **Inputs** — `specs/skilljar-v1-openapi.yml`, `specs/skilljar-v2-openapi.json`, a stored registry
  snapshot; optionally `CSA_SKILLJAR_V2_*` for the authenticated checks
- **Outputs** — a diff report in the job log; a GitHub issue when anything changed
- **Serves** — the project's central premise. The coverage map has a shelf life (GOALS "shrink";
  `WAITING-FOR-001`), and this is the mechanism that notices, so retirement is triggered by
  evidence rather than by someone remembering to look.
- **Reads from** — `api.skilljar.com` (spec documents, authorization-server metadata, endpoint
  probes), `mcp.skilljar.com` (tool registry, credentials permitting)
- **Writes to** — GitHub Issues on this repo
- **Backfill** — `none`
- **Cadence** — weekly is deliberate. Skilljar ships on a release cadence measured in months; a
  daily check would be noise, and a quarterly one would let a whole phase get built against a gap
  that had already closed.
- **Health check** — the job runs and reports; a run that finds nothing must say so explicitly.
  Per ZERO-DEFECT, silence is not health — "no drift" and "the check ran" are two separate facts
  and both get reported.
- **Runbook** — on an opened issue: confirm the change by hand, then decide whether it triggers a
  v1 family retirement (`WAITING-FOR-001`), a parity-surface update (ADR-006), or only a snapshot
  refresh. Update `specs/` in the same PR as any code change so the baseline and the code move
  together.
- **Owner** — Kurt Seifried
- **Last touched** — 2026-08-26 (shipped)
- **Next review** — 2026-11-26
- **Notes** — Degrades gracefully without credentials: the spec and scope-catalogue checks need no
  authentication, the registry check does. A skipped check is reported as skipped, never as passed.
