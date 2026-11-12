# AGENTS.md

Tightened for modern AI: 2026-11-12.

Instructions for every AI agent working in this repository. `CLAUDE.md` and `GEMINI.md` are
one-line pointers to this file: **do not edit them.** Put every instruction here, and label one
that applies to a single tool with that tool's name
([DEC-033](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/DECISIONS.md#dec-033-agentsmd-is-the-instruction-file-claudemd-and-geminimd-are-one-line-pointers-never-full-files)).

`csa-skilljar` (import name `csa_skilljar`) is a Python library and local stdio MCP server over
**both** Skilljar REST APIs. It reproduces the official Skilljar MCP server's tool surface
exactly, then adds the capabilities that exist only in v1. It is shipped: on PyPI, and installed
on staff machines by DesktopSetup. Read the version from `__version__` in
`src/csa_skilljar/__init__.py` and `CHANGELOG.md`, not from prose that restates it.

## Honesty

- **No write has ever run against real Skilljar. Never describe writes as verified.** Reads run
  against the production organization; writes have only run against `FakeBackend`. `v1.0.0`
  waits on [`WAITING-FOR-003`](WAITING-FOR/WAITING-FOR-003.md).
- **Don't describe unimplemented things as working.** Keep `README.md` (its status banner
  included) and `CHANGELOG.md` in step with what lands.
- **Be accurate and fair about Skilljar in public text.** Their first-party server is good and
  this project complements it: describe differences factually, without disparagement. The repo
  is public and carries CSA's name.

## Credentials and learner data

Probe output and API responses hold real learners' names and email addresses.

- **Credential issuance and scoping are never delegated to AI** ([`RACI.md`](RACI.md)). Never
  create, request or rotate a Skilljar credential.
- **Never commit credentials.** `.env` is gitignored in this repo itself: a public repo must not
  rely on anyone's global config.
- **Never commit API response bodies.** Record counts and shapes, never rows. `.gitignore`
  covers the known patterns; the judgement is still yours.
- **Hand-write a redacting `__repr__`** for any domain object holding learner data: embedders
  log them, and the default dump is a data leak.
- **Never interpolate a credential into an error message.** Chain the cause; keep the message
  generic.
- **No caching, no persistence** ([`DATA-RESOURCES.md`](DATA-RESOURCES.md),
  [`DATA-NEEDS.md`](DATA-NEEDS.md)). Either changes the security posture and needs its own ADR.
- **Any change that surfaces course content to a model** is constrained by the prompt-injection
  analysis in [`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md).
- **The one deviation from ZERO-DEFECT, ZD-13 (secrets in a secrets manager).** Credentials
  arrive as `CSA_SKILLJAR_*` environment variables, set in the MCP client's config or read from
  the file that `CSA_SKILLJAR_ENV_FILE` names (parsed, never executed; only `CSA_SKILLJAR_*`
  keys; an already-set variable wins). Compensating controls: the server writes
  nothing to disk (`client_credentials` needs no token cache); credentials never appear in a
  message, log or `__repr__`; scopes are narrowed per install. Revisit if it is ever hosted.

## Architecture

ADR-002 (fact 1) and ADR-004 (fact 2) are load-bearing: don't contradict them without a
superseding ADR.

1. **Routing is absolute: v2 owns every capability v2 has; v1 serves only what v2 lacks.** No
   fallback, no dual-routing; each capability has exactly one owner. v2 is JSON:API with cursor
   pagination and v1 a flat DRF envelope, so a fallback degrades silently (ADR-002).
2. **No version marker in any tool name, ever.** When webhooks reach v2, one backend changes and
   `list_webhooks` keeps its name (ADR-004).
3. **Enforcement wraps the backend seam; it is not a check in the tools.** `PolicyBackend` fails
   closed: a backend method with no declared gate is refused, not delegated. Library embedders
   get the same guarantee as MCP clients.
4. **Two independent credentials, both optional.** v1 is HTTP Basic (API key as username, empty
   password); v2 is OAuth `client_credentials`. All four states (both, v2 only, v1 only,
   neither) start the server.
5. **`client_credentials`, not `authorization_code`** (ADR-003). The official server is remote and
   acts for a browser user; running locally removes the browser, redirect URI, consent flow and
   token cache. There is no login ([`FRICTION-004`](FRICTION/FRICTION-004.md)).
6. **Parity is additive** (ADR-006). Tool and argument names are identical to the official
   server's, plus *optional* parameters where theirs lacks something. A caller sending exactly
   what the official server accepts gets exactly what it returns.

## Invariants that fail silently: check them when editing

From `csa-google-workspace`, verified against `mcp` 2.1.0
([PYTHON-SDK-TRAPS](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/research/mcp-servers/PYTHON-SDK-TRAPS.md)).
Tests and comments cite them by number.

1. **Nothing may touch stdout.** Under stdio it *is* the JSON-RPC channel: one stray byte and the
   server looks alive while answering nothing. Diagnostics go to stderr, and a test asserts no
   reachable configuration writes to stdout.
2. **Raise `ToolError`, never a plain exception.** Anything else becomes `UnexpectedToolError`
   with its message discarded. One translation decorator at the tool boundary.
3. **Never use `Field(alias=…)` on a tool parameter.** It publishes a correct schema and then
   fails every call. A camelCase wire name must be the literal Python parameter name.
4. **`mcp.server.fastmcp` does not exist.** It is `from mcp.server import MCPServer`; keep
   `mcp>=2.1` pinned. Models write the old import confidently.
5. **Sync tool handlers run on worker threads** (`anyio.to_thread.run_sync`). A non-thread-safe
   client must be thread-local, never shared.
6. **`TypedDict` comes from `typing_extensions`:** below Python 3.12, pydantic silently emits no
   schema otherwise. No supported Python is below 3.12 while `requires-python` is `>=3.14`; the
   rule stays because that floor is policy (DEC-025) and may come back down.
7. **Never block `initialize` on a network call.** A slow Skilljar would become an opaque "server
   failed to start". Startup is two tiers: synchronous config presence, then a background
   validity probe.

## Zero defect

[ZERO-DEFECT.md](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/ZERO-DEFECT.md)
applies.

- **Handle every error explicitly (ZD-1).** No swallowed exceptions; say which failure it was.
- **Generate errors aggressively (ZD-2).** A `200` whose body is not a JSON object is an error.
  An unknown API path is a loud error: `scopes_for()` returning `()` legitimately means
  "declared, needs no scope", and conflating that with a typo silently disables the scope
  pre-check.
- **Silence is not health (ZD-17).** Of every branch that concludes there is no work, ask: if
  this fired forever, would anyone notice?
- **Tests produce two signals (ZD-12).** `tests/conftest.py` fails any test that logs at `ERROR`;
  it is scoped to `ERROR` because several tests assert on `WARNING` output.
- **Never suppress command output** (`cmd >/dev/null && echo ok`): a suppressed failure looks
  like a pass.
- **A check that cannot fail is theatre.** Mutation-test every guard once: break what it
  protects, watch it fail, restore.
- **Coverage is 100%, statements and branches, and `fail_under = 100` is the gate.** Never lower
  it. The only hatch is `# pragma: no cover` with its reason at the line, each one paired with a
  test that pins its premise.
- **Prefer a census to per-tool tests where the property is uniform:** derive the population
  from the signatures or the live registry, so a new tool is covered without anyone remembering.
  Then review the population and the baseline, not the assertion: print the derived set and read
  it, make sure the fixture is not so empty that the unfiltered call already passes, and give
  every member a potency case that fails by name
  ([`FRICTION-005`](FRICTION/FRICTION-005.md)).

## How to work here

- **Branch and PR for every change; never commit to `main`.** Prefixes: `feat/`, `fix/`,
  `docs/`, `chore/`.
- **Run `./scripts/verify.sh` before every commit, and act on its exit code.** It runs tests,
  lint, types, security and doc claims with nothing suppressed. `.githooks/pre-commit` enforces
  it once `git config core.hooksPath .githooks` is set.
- **Plan, then execute.** Write the spec or plan under `docs/superpowers/`, then implement TDD
  against `FakeBackend`.
- **Read the design spec before proposing anything,** `GOALS.md` and `BUSINESS-CASE.md` before
  proposing a scope change, and `TODO.md`'s consideration pile before proposing a "missing"
  feature.
- **Inventory before declaring a blocker.** Before asking the user for X, look for it: `.env` in
  the working directory, environment variables, existing config, connected services.
- **Probe before asking.** If a free, read-only, side-effect-free action answers the question
  (an unauthenticated discovery document, a `401`-vs-`404` existence probe, a published spec),
  take it.
- **Probe beats docs.** Vendor prose about this API has been wrong repeatedly
  ([`FRICTION-002`](FRICTION/FRICTION-002.md)). When it and a probe disagree, the probe wins and
  the finding goes in the spec.
- **Re-check upstream before claiming a gap:** `scripts/check_upstream.py`.
- **Harvest perishable access.** When access is human-gated, temporary or about to be revoked,
  capture everything on first contact, not only what the current question needs
  ([`FRICTION-001`](FRICTION/FRICTION-001.md)).
- **Complete a convention.** When a documented convention determines a set of artifacts (the
  CINO project file set, the public-repo checklist), produce the whole set.
- **Log friction** in [`FRICTION.md`](FRICTION.md). The bar is low: an annoyance, for a human or
  an AI.
- **Check the "Next review" date** in [`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md)
  against today.
- **[CSA public repo standards](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/PUBLIC-GITHUB-REPO-STANDARDS.md)
  apply:** Actions pinned to commit SHAs, releases through Trusted Publishing
  ([`RELEASING.md`](RELEASING.md)).

[`FRICTION-003`](FRICTION/FRICTION-003.md) records why the operating rules above and the
autonomy contract below exist.

## Autonomy

**Proceed without asking:** read-only probes of anything; local file work; branches, PRs, and
merging documentation PRs on green; running tests; following a documented convention to
completion.

**Ask first:** anything that creates state on a third party (registering OAuth clients, filing
issues on other people's repos); publishing (PyPI, public repos); credential issuance or scoping;
destructive local operations; anything the design spec lists as a non-goal.

## Commands

**Always work inside a virtual environment. Never `pip install` into a system or user Python,
and never run a bare `pytest`, `ruff` or `mypy`:** they resolve to whatever is on `PATH`, and a
global `mcp` 1.x still has `mcp.server.fastmcp`, so a suite can pass against the wrong API.
Users install with `uv tool install csa-skilljar` (DEC-012) or `pipx`; a plain `pip install`
into a system Python is unsupported.

```bash
./scripts/verify.sh                         # everything CI checks, no suppressed output

python3.14 -m venv .venv                    # requires-python >=3.14; .python-version still says 3.12 (#132)
.venv/bin/python -m pip install -e ".[dev]"

.venv/bin/python -m pytest -q               # offline: no network, no credentials
.venv/bin/ruff check src tests scripts
.venv/bin/mypy
.venv/bin/python -m pytest -q --cov --cov-report=term-missing   # what CI's test job runs

CSA_SKILLJAR_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/   # real Skilljar, opt-in
.venv/bin/python scripts/check_docs.py      # doc claims vs artifacts; a required CI check
.venv/bin/python scripts/check_upstream.py  # live Skilljar vs specs/
```

## Reference

- **`docs/superpowers/specs/2026-08-26-csa-skilljar-design.md`**: the authoritative design.
  Architecture, routing rule, credential model, error taxonomy, phasing, and probe-verified facts.
- **`specs/`**: upstream OpenAPI snapshots from 2026-08-26, someone else's moving target, and
  already drifted. [`specs/PROVENANCE.md`](specs/PROVENANCE.md) holds each file's identity and the
  last full diff; the weekly drift issues give the current gap
  ([#122](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/122)).
- **`analysis/`**: the 66-entity reconciliation of both APIs, the live OAuth scope catalogue, and
  a surface map. The authorization server advertises **88 scopes** while the published v2 spec
  uses **28**; the rest are Skilljar's roadmap (`WAITING-FOR-001`). `scripts/check_docs.py`
  asserts these three numbers.
- **`docs-html/`**: the rendered vendor pages, kept for provenance only.
- **`TODO.md`**: the index of all open work. With open GitHub Issues, it finds everything.
- **`DECISIONS-ADR.md`** / **`DECISIONS-PRD.md`**: technical decisions with their rejected
  alternatives; scope, audience and what is out.
- **`WAITING-FOR.md`**: external conditions with observable triggers. 001 retires each v1 family
  once v2 ships it; 003 gates live writes.
- **The README's "Project documentation" table** lists the rest: `ROADMAP.md`, `GOALS.md`,
  `BUSINESS-CASE.md`, `RACI.md`, `BACKUP-RESOURCES.md` and more.
