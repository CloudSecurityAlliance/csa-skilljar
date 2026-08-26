# TODO

Index of **all** open work on this project. One line per item; detail lives in GitHub Issues, the
design spec, or the logs this file points at. Per the CINO todo-index convention, sweeping this
file plus open GitHub Issues finds everything.

**Status: design complete, nothing implemented.**

## Blocked / waiting

- Obtain a v2 OAuth client (id + secret) scoped for development — blocks all of Phase 1 → `WAITING-FOR-002`
- v2 endpoints for webhooks, paths, assets, commerce — reserved scopes, not built → `WAITING-FOR-001`

## Next (Phase 1 — parity)

- Write the implementation plan from the approved design spec
- `pyproject.toml`, `src/` layout, typed marker, single-sourced version
- `Backend` protocol + `V2Backend` + `FakeBackend` + conformance test
- `PolicyBackend` with fail-closed `_GATES`, and the hand-written capability expectation matrix
- The 73 official tools over v2, with additive-compatibility optional parameters
- Auth: `client_credentials` grant, the seven-state error taxonomy, local scope pre-check
- Two-tier startup checks (config presence synchronous → validity in background)
- `describe_capabilities` — always registered, reports what exists but is not enabled
- Test asserting nothing reachable writes to stdout
- `scripts/check_upstream.py` + weekly CI job
- CI: lint, type-check, test matrix, coverage floor, security scan — all required checks
- Branch protection enforced for admins, once the checks above exist
- `SECURITY.md` and `RELEASING.md` (deliberately deferred from the scaffold PR)

## Later (Phases 2–9)

- Phase 2 — remaining v2 credential administration, behind an `admin` profile, off by default
- Phase 3 — learner progress · Phase 4 — assets and media · Phase 5 — commerce (read-biased)
- Phase 6 — learning paths · Phase 7 — events and webhooks · Phase 8 — ILT/vILT · Phase 9 — labels and tags
- The demonstration-as-end-to-end-test, once there are enough tools for it to be worth running

## Consideration pile

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
