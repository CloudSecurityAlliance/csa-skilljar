# TODO

Index of **all** open work on this project. One line per item; detail lives in GitHub Issues, the
design spec, or the logs this file points at. Per the CINO todo-index convention, sweeping this
file plus open GitHub Issues finds everything.

**Status: design complete, nothing implemented.**

## Blocked / waiting

- Obtain a v2 OAuth client (id + secret) scoped for development — blocks all of Phase 1 → `WAITING-FOR-002`
- v2 endpoints for webhooks, paths, assets, commerce — reserved scopes, not built → `WAITING-FOR-001`

## Next — Block 1: a working server (v0.0.1)

- ~~Write the Block 1 implementation plan~~ — done: `docs/superpowers/plans/2026-08-26-block-1-working-server.md`
- `pyproject.toml`, `src/` layout, typed marker, single-sourced version
- `Backend` protocol + `V2Backend` + `FakeBackend` + conformance test
- `PolicyBackend` with fail-closed `_GATES`, and the hand-written capability expectation matrix
- Auth: `client_credentials` grant, the seven-state error taxonomy, local scope pre-check
- Two-tier startup checks (config presence synchronous → validity in background)
- Tool: `check_access` — which credentials work and what each unlocks
- Tool: `describe_capabilities` — always registered; what exists but is not enabled
- Tool: `report_a_problem` — version, OS, Python, active policy; no ids, no credentials
- Tool: `list_courses` — one real read, so "it works" means something
- `--version` on stderr, reachable with no MCP client in the loop
- Test asserting nothing reachable writes to stdout
- CI: lint, type-check, test matrix, coverage floor, security scan — all required checks
- Branch protection enforced for admins, once the checks above exist
- `SECURITY.md` and `RELEASING.md` (deliberately deferred from the scaffold PR)
- `scripts/check_upstream.py` + weekly CI job
- Model-in-the-loop cold-use test for tool descriptions (contract documented in Task 13; harness lands Block 2)
- Replace `check_access`'s reach through `client._backend._backend._creds` with a
  `SkilljarClient.credential_status()` accessor before more callers depend on the shape

## Later (Blocks 2–17)

- Blocks 2–9 — parity: courses & lessons · quizzes & questions · question banks & bindings ·
  enrolment & reporting · students · groups & signup fields · publishing & catalog ·
  web packages & OAuth client. **Parity complete at Block 9 (v0.8.0).**
- Block 10 — remaining v2 credential administration, behind an `admin` profile, off by default
- Block 11 — v1 foundation + learner progress
- Blocks 12–17 — assets · commerce (read-biased) · paths · webhooks · vILT/ILT · labels & tags
- The demonstration-as-end-to-end-test, once there are enough tools for a tour to be worth taking (after Block 5)

## Consideration pile

- **Lockfile for CI?** `pyproject.toml` pins floors (`httpx>=0.27`, `mcp>=2.1`), not exact
  versions. PUBLIC-GITHUB-REPO-STANDARDS says "consider a lockfile for CI". A library
  should not over-pin what it imposes on consumers, but CI could resolve against a lock so
  a green run means something specific. Decide before v0.1.0.

Not committed to; recorded so they are not rediscovered.

- Should the integration suite use the broad `CINO_READ_ONLY_TESTING_KEY`, or a narrower key?
- Is a `PlaywrightBackend` ever warranted for genuinely API-impossible operations?
- Should `check_upstream.py` publish its findings somewhere shared rather than one repo's issues?
- Does the surface-map artefact belong in the repo as generated output, or regenerated on demand?

## Pointers

- Sequence and block plan → `ROADMAP.md`
- Decisions → `DECISIONS-ADR.md`, `DECISIONS-PRD.md`
- Waiting on external conditions → `WAITING-FOR.md`
- Friction → `FRICTION.md`
- Bugs and discrete work → [GitHub Issues](https://github.com/CloudSecurityAlliance/csa-skilljar/issues)
