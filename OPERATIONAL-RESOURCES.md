# Operational Resources

Recurring operational work. This project deploys no service and runs no infrastructure — it is a
library and a local process on the user's machine — so both entries are about watching someone
else's surface rather than running our own: one scheduled and automatic, one manual because it
needs a human to clear a login.

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
- **Health check** — three exit codes, kept distinct on purpose: `0` no drift, `1` Skilljar
  moved (files an issue), `2` could not reach Skilljar (an outage, files nothing). The first
  scheduled run failed on one transient SSL timeout among 34 probes and reported identically
  to real drift; an outage that looks like a finding trains people to ignore findings.
  A run that finds nothing must say so explicitly.
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

## check_dashboard — dashboard grading-queue drift detection

- **What it does** — Fetches the dashboard's undocumented `/tasks/ajax` DataTables endpoint and one
  `/tasks/grade-quiz/<id>` grading page, and checks the shape both by hand: the expected
  `display`/`sort`/`filter` columns, the `/tasks/grade-quiz/` anchor `list_tasks`/`get_task` parse
  the task id out of, and the grading form's `csrfmiddlewaretoken` / `quiz_response_id` /
  `email_student_on_completion` / `question-response-*` fields. There is no OpenAPI document for
  these endpoints for `check_upstream.py` to diff, so this is the hand-written substitute; without
  it a Skilljar UI release surfaces as an empty grading queue rather than as a detected problem.
- **Tier** — `manual`
- **Status** — `production`
- **Code** — `scripts/check_dashboard.py`
- **Runtime** — Python, local only
- **Schedule** — manual, run before relying on `list_tasks`/`get_task` after a Skilljar UI change
  is suspected. **Needs a live, logged-in dashboard session, so it cannot run unattended in CI** —
  the login is hCaptcha-protected and only a human can clear it
  (`scripts/capture_dashboard_session.py`); there is no service-account credential to hand to a
  scheduled workflow the way `CSA_SKILLJAR_V2_*` is handed to `upstream.yml`.
- **Inputs** — `CSA_SKILLJAR_DASHBOARD_SESSION` (a Playwright storage-state file from
  `scripts/capture_dashboard_session.py`); live `dashboard.skilljar.com`
- **Outputs** — a report on stdout/stderr; no issue filed, no state written anywhere
- **Serves** — keeps `list_tasks`/`get_task` (the only place the grading queue is reachable at all
  — neither Skilljar API exposes it) from silently going dark. See
  `docs/superpowers/specs/2026-09-02-dashboard-backend-design.md`.
- **Reads from** — `dashboard.skilljar.com` (`/tasks/ajax`, `/tasks/grade-quiz/<id>`)
- **Writes to** — nothing
- **Backfill** — `none`
- **Health check** — three exit codes, kept distinct on purpose: `0` healthy, `1` drift detected
  (lists the specific problems), `2` could not check — an unreachable host, or a session that has
  expired or was never configured (named explicitly, with the capture-script remedy). Modelled on
  `check_upstream.py`'s own exit-2 contract after issue #13 filed a TLS handshake timeout as
  upstream drift and it sat open for five days while real drift went unnoticed; an outage or an
  expired session must never look like a finding here either.
- **Runbook** — on exit 1: confirm the change by hand against the live dashboard, then update
  `csa_skilljar/dashboard.py`'s parsing (the regexes and expected columns/fields) and this script's
  `EXPECTED_COLUMNS`/`EXPECTED_FORM_FIELDS` together. On exit 2: re-run
  `scripts/capture_dashboard_session.py` and try again before concluding anything about drift.
- **Owner** — Kurt Seifried
- **Last touched** — 2026-09-02 (shipped)
- **Next review** — 2026-12-02
- **Notes** — Cheaper than it looks: no OAuth, no OpenAPI diff, just two GETs with a session
  cookie. The cost is entirely the human login step, which is also why it is `manual` rather than
  `simple-scheduled` like `check_upstream.py`.
