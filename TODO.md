# TODO

Index of **all** open work on this project. One line per item; detail lives in GitHub Issues, the
design spec, or the logs this file points at. Per the CINO todo-index convention, sweeping this
file plus open GitHub Issues finds everything.

**Status: all seventeen blocks on `main` — 112 tools (84 v2, 27 v1, plus `demonstration_plan`). Released to PyPI through v0.15.0. v1.0.0 waits on live write verification → `WAITING-FOR-003`. The largest open body of work is the 23-issue security-audit backlog → [#76](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/76).**

## Blocked / waiting

- Obtain a v2 OAuth client (id + secret) scoped for development → `WAITING-FOR-002`.
  **Blocks only the v0.0.1 release**, not development — Block 1 was built entirely
  offline against `FakeBackend`, and Block 2 can be too.
- v2 endpoints for webhooks, paths, assets, commerce — reserved scopes, not built →
  `WAITING-FOR-001`. Watched by `scripts/check_upstream.py`.

## Next

- **23 open issues from security audit `2026-08-30-01` → [#76](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/76).**
  This is the largest body of open work on the project and it is tracked in GitHub, not
  here, per the todo-index convention. Two things to read before picking any of them off:
  - **[#54](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/54) gates
    [#55](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/55).** The top
    finding's severity depends on whether Skilljar sanitises `content_html` on render,
    which cannot be settled from this repository. Test it against an isolated *unpublished*
    course with guaranteed teardown — a payload in a published lesson is a live
    vulnerability you created.
  - **[#66](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/66) closes a
    class.** Five findings are one pattern: a hand-maintained description drifting from the
    policy it describes. Patching the five leaves the sixth instance equally invisible. The
    same pattern produced four separate defects between 2026-08-30 and 08-31 — the stale v1
    credential message, `CSA_SKILLJAR_ENV_FILE` being set and ignored, and two stale status
    banners — so this is the highest-leverage item in the set.
  - [#63](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/63) is **half done**:
    v0.15.0 fixed both stale strings. What remains is that a **v1-only install can call no
    tool at all** — `ClientProvider.__call__` raises on the missing v2 credential before the
    v1 backend is constructed. Verified still broken 2026-08-31.

- **Skilljar shipped `/v2/assets/` — ADR-002's retirement trigger has fired for the first
  time.** Live v2 has 46 paths against 44 in `specs/`; the new ones are `/v2/assets/`
  (GET, POST, PATCH) and `/v2/assets/{id}` (GET, DELETE). Probed 2026-08-31: **403
  `permission_denied`, not 404** — it exists and serves, and our client simply lacks the
  scope. Skilljar now advertises `assets:read` and `assets:write`; our client holds 17
  scopes and none of them are for assets.
  - Block 12 built `list_assets` / `get_asset` over **v1 precisely because v2 had no assets
    endpoint**. ADR-002 says v2 owns every capability v2 has, so they must be re-pointed;
    ADR-004 says the tool names do not change. This is the exact scenario the
    no-version-in-tool-names rule exists for.
  - **Needs Kurt:** the OAuth client re-issued with `assets:read`. Credential issuance is
    never delegated to AI (`RACI.md`).
  - Then re-take the snapshot in `specs/` and close the drift issue.

- **Writes to Skilljar are OFF** → `WAITING-FOR-003`. Enforced by `ReadOnlyClient` in
  `tests/integration/conftest.py`, not by convention. Needs Hannah: is there a sandbox,
  or a fixture convention for throwaway courses/students? Until then live tests read only.
- Consider re-issuing the dev OAuth client **read-only**. It currently holds
  `courses:write`, `lessons:write`, `quizzes:write`, `question-banks:write`, which nothing
  needs yet — dropping them removes the last write path rather than guarding it.

- **All seventeen blocks are done.** What v1.0.0 waits on is live write verification →
  `WAITING-FOR-003`. Every read is exercised against production; no write has been.
- Run `demonstration_plan(mode="read_write")` once `WAITING-FOR-003` closes. The
  read-only half has been executed against production - 52 of 61 steps, 2 refusals both
  correctly predicted. The write half has never run anywhere but the fake.
- `license-packages` and `access-code-pools` are still empty in the reference org and
  were skipped in Block 13. Worth a tool only if they ever get used.
- `/v1/web-packages/{id}/lessons` — attaching a package to lessons, the one v1-only
  web-package capability. A write, so it waits on `WAITING-FOR-003` like the rest.
- **Per-lesson progress is not available from Skilljar.** The documented v1 endpoint
  404s; see the Block 11 correction in `ROADMAP.md`. Worth re-probing if Skilljar ships
  it, since it is the one thing a progress question usually means.
- Model-in-the-loop cold-use test for tool descriptions (contract documented in
  `tests/test_descriptions.py`; harness lands with Block 2)

## Done (Block 1, shipped to main 2026-08-26)

Recorded because a stale index is worse than none — these were open lines until the
work landed, and leaving them would make the sweep lie.

- ~~Block 1 implementation plan~~ → `docs/superpowers/plans/2026-08-26-block-1-working-server.md`
- ~~Packaging, `src/` layout, typed marker, single-sourced version~~
- ~~`Backend` protocol + `V2Backend` + `FakeBackend` + conformance test~~ (covers both impls)
- ~~`PolicyBackend` with fail-closed `_GATES` + hand-written capability matrix~~
- ~~Auth: `client_credentials`, seven-state error taxonomy, local scope pre-check~~
- ~~Two-tier startup checks~~
- ~~Tools: `check_access`, `describe_capabilities`, `report_a_problem`, `list_courses`~~
- ~~`--version` on stderr with no MCP client in the loop~~
- ~~Test asserting nothing reachable writes to stdout~~
- ~~CI: lint, type-check, test matrix, coverage floor, security scan~~
- ~~Branch protection enforced for admins~~
- ~~`SECURITY.md`~~ · ~~Dependabot (pip + github-actions)~~
- ~~`scripts/check_upstream.py` + weekly CI job~~
- ~~Block 2 — courses & lessons (8 tools), shipped to `main` 2026-08-27~~
- ~~Block 3 — quizzes & questions (10 tools), shipped to `main` 2026-08-27~~
- ~~Block 4 — question banks & bindings (9 tools), shipped to `main` 2026-08-27~~
- ~~Block 5 — enrolment & reporting (9 tools), shipped to `main` 2026-08-27~~
- ~~Block 6 — students (8 tools), shipped to `main` 2026-08-27~~ — the four destructive
  tools sit behind `people.destructive`, which no named profile but `full` grants.
  `SECURITY-RESOURCES.md` carries the dated review.
- ~~Block 7 — groups & signup fields (11 tools), shipped to `main` 2026-08-27~~ — seven
  named traps, each with a regression test and a killed mutation.
- ~~Block 8 — publishing & catalog (12 tools), shipped to `main` 2026-08-27~~ — new
  `publishing.*` capability; visibility overrides routed to `groups.*` to match the
  upstream scope.
- ~~Block 9 — web packages & OAuth client (6 tools), shipped to `main` 2026-08-27~~ —
  **73-tool parity complete and asserted by `tests/test_parity.py`.**
- ~~Block 10 — credential administration (8 tools), shipped to `main` 2026-08-27~~ —
  first work past parity; closes the mint-without-audit asymmetry.
- ~~End-to-end stdio suite (`tests/e2e/`), shipped to `main` 2026-08-27~~ — found an
  empty `serverInfo.version`, and a stale pipx install that the first draft of the
  suite was happily testing instead of this checkout.
- ~~Replace `check_access`'s private-attribute reach~~ → `SkilljarClient.credentials`

## Later (Blocks 2–17)

- Blocks 2–9 — parity: courses & lessons · quizzes & questions · question banks & bindings ·
  enrolment & reporting · students · groups & signup fields · publishing & catalog ·
  web packages & OAuth client. **Parity complete at Block 9 (v0.8.0).**
- Block 10 — remaining v2 credential administration, behind an `admin` profile, off by default
- Block 11 — v1 foundation + learner progress
- Blocks 12–17 — assets · commerce (read-biased) · paths · webhooks · vILT/ILT · labels & tags
- **`demonstration_plan` — the end-to-end tour.** 76 tools now, so the "after Block 5"
  condition is long met. Two constraints it must carry, both decided 2026-08-27:
  - **Reads only.** Writes are off → `WAITING-FOR-003`. The plan should say up front
    which steps it is skipping and why, rather than quietly omitting them.
  - **Named accounts only** — `@cloudsecurityalliance.org` and `kurt@seifried.org`, per
    `DATA-RESOURCES.md`. A transcript persists, and the org holds 42,669 real learners.
    Note `filter[email]` is EXACT — Skilljar cannot filter by domain, so the plan has to
    start from specific addresses and scope every learner read by the resolved student
    id. It cannot narrow a broad listing after the fact.

## Consideration pile

- **Lockfile for CI?** `pyproject.toml` pins floors (`httpx>=0.27`, `mcp>=2.1`), not exact
  versions. PUBLIC-GITHUB-REPO-STANDARDS says "consider a lockfile for CI". A library
  should not over-pin what it imposes on consumers, but CI could resolve against a lock so
  a green run means something specific. Decide before v0.1.0.

Not committed to; recorded so they are not rediscovered.

- Should the integration suite use the broad v1 key in `CSA_SKILLJAR_V1_API_KEY`, or a narrower one?
- Is a `PlaywrightBackend` ever warranted for genuinely API-impossible operations?
- Should `check_upstream.py` publish its findings somewhere shared rather than one repo's issues?
- Does the surface-map artefact belong in the repo as generated output, or regenerated on demand?

## Pointers

- Sequence and block plan → `ROADMAP.md`
- Decisions → `DECISIONS-ADR.md`, `DECISIONS-PRD.md`
- Waiting on external conditions → `WAITING-FOR.md`
- Friction → `FRICTION.md`
- Bugs and discrete work → [GitHub Issues](https://github.com/CloudSecurityAlliance/csa-skilljar/issues)
