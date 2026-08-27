# TODO

Index of **all** open work on this project. One line per item; detail lives in GitHub Issues, the
design spec, or the logs this file points at. Per the CINO todo-index convention, sweeping this
file plus open GitHub Issues finds everything.

**Status: Block 1 shipped to `main`. Not yet released — v0.0.1 needs `WAITING-FOR-002`.**

## Blocked / waiting

- Obtain a v2 OAuth client (id + secret) scoped for development → `WAITING-FOR-002`.
  **Blocks only the v0.0.1 release**, not development — Block 1 was built entirely
  offline against `FakeBackend`, and Block 2 can be too.
- v2 endpoints for webhooks, paths, assets, commerce — reserved scopes, not built →
  `WAITING-FOR-001`. Watched by `scripts/check_upstream.py`.

## Next

- Release v0.1.0 — needs `WAITING-FOR-002`; everything else for it is done
- Block 3 — quizzes & questions (10 tools) → `ROADMAP.md`
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
- ~~Replace `check_access`'s private-attribute reach~~ → `SkilljarClient.credentials`

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
