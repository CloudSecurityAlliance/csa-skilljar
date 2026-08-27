```
project_tracker_base: CINO Project Tracker:appf7fRQUvY9Iy7sL
project_tracker_table: Projects:tblchmbxSAavvJKaY
project_tracker_record: csa-skilljar:recbwfx6O30BboQNv
project_source: github:CloudSecurityAlliance-Internal/CINO-Projects/projects/CloudSecurityAlliance/csa-skilljar
```

# csa-skilljar

A Python library and local MCP server for the [Skilljar](https://www.skilljar.com/) customer
education platform, covering **both** of Skilljar's REST APIs — v1 and v2 — behind one set of
tools.

> **Status: Blocks 1–2 implemented, not yet released.**
>
> Eleven tools over Skilljar's v2 API. Install from source until the first PyPI release:
> `pipx install git+https://github.com/CloudSecurityAlliance/csa-skilljar`
> | | |
> |---|---|
> | **Server** | `check_access` · `describe_capabilities` · `report_a_problem` |
> | **Courses** | `list_courses` · `get_course` · `create_courses` · `update_courses` |
> | **Lessons** | `list_lessons` · `get_lesson` · `create_lessons` · `update_lessons` |
>
> The full 73-tool parity surface arrives over Blocks 3–9; see [ROADMAP.md](ROADMAP.md).

## Start with Skilljar's official MCP server

**If you want Skilljar in an AI client, use [Skilljar's own MCP server](https://mcp.skilljar.com/mcp).**
That is the right default and we recommend it without reservation. It is first-party, hosted and
maintained by the vendor, needs nothing installed on your machine, covers the whole v2 API in 73
tools, and authenticates with OAuth and per-operation scopes. Skilljar are actively building v2
out, so it gets better on their release cadence rather than ours.

```bash
claude mcp add skilljar --transport http https://mcp.skilljar.com/mcp
```

Try that first. For most people it is the whole answer.

## …but if you need more

Some things are not in the v2 API yet, so no v2 client can reach them. The v1 API is considerably
larger — 340 operations against v2's 82 — and today it is the only way to get at:

- **per-lesson learner progress** — v2 reports course-level completion only
- **webhooks** — v2 has no event notifications at all
- **asset upload** — v2 has no file upload
- **learning paths**, **instructor-led training**, and the **commerce stack**
  (offers, promo codes, purchases, training credits)

`csa-skilljar` exists for that gap. It reproduces the official tool surface exactly — same tool
names, same argument names — and then adds the v1-only capabilities alongside them, so you do not
have to choose between the two APIs or run two servers.

It also runs locally over stdio, which some organisations need: your API credentials stay on your
own machine.

**We expect this project to shrink over time, and that is the intended outcome.** Skilljar has
publicly reserved OAuth scopes for webhooks, paths, assets, tags and commerce. As those endpoints
ship, the corresponding v1 support here gets retired in favour of v2 — the tool names stay the
same and callers notice nothing.

| | Official Skilljar MCP | csa-skilljar |
|---|---|---|
| APIs | v2 | v1 + v2 |
| Transport | remote HTTP | local stdio |
| Credentials | held server-side | stay on your machine |
| Auth | OAuth authorization code (browser) | OAuth client credentials + v1 API key |
| Capability control | OAuth scopes at consent | scopes **plus** per-install profiles |
| Library | — | the library is the product too |

## Checking the state of Skilljar's v2 API

Skilljar's v2 API is actively growing, and the official MCP server tracks it closely. That is good
news for everyone — and it means the coverage map in this project has a shelf life. **Before
assuming a gap documented here is still a gap, re-check upstream.**

```bash
# 1. The published v2 surface
curl -s https://api.skilljar.com/v2/openapi.json | jq '.paths | keys | length'

# 2. The declared scope catalogue — a leading indicator of what is coming
curl -s https://api.skilljar.com/.well-known/oauth-authorization-server \
  | jq -r '.scopes_supported[]'

# 3. The official MCP server's live tool list
#    Connect it, then run /mcp in Claude Code.
```

At the time of writing, the scope catalogue advertises **88 scopes** while the published v2 spec
uses **28** — areas including webhooks, paths, assets, tags and commerce have scopes reserved but
no endpoints yet. When those endpoints ship, the v1 fallbacks this project provides for them
should be retired in favour of v2, and this note updated.

`scripts/check_upstream.py` will automate all three and report drift against the snapshots in
`specs/`. Until then, run the commands above.

## Credentials

Two independent credentials, both optional. The server starts with either, both, or neither, and
tells you what is available.

| Variable | For | Obtain from |
|---|---|---|
| `CSA_SKILLJAR_V1_API_KEY` | the v1 API | Skilljar Dashboard — see [Skilljar's API guide](https://support.gainsight.com/Skilljar/Develop_and_Customize/API/Getting_started_with_the_Skilljar_API) |
| `CSA_SKILLJAR_V2_CLIENT_ID` / `CSA_SKILLJAR_V2_CLIENT_SECRET` | the v2 API | Skilljar Dashboard, v2 API clients |

We link Skilljar's own documentation rather than transcribing their dashboard navigation, which
we cannot keep current.

Scope the v2 client to what you actually need. The API declares a required scope on every
operation, and the sensitive ones are separable — `students:anonymize` (irreversible),
`students:deactivate`, and `students:manage-password` can all be withheld from a client used for
content authoring.

## What it will cover

Reproduces all 73 official tools, then adds v1-only families in this order:

1. **Learner progress** — per-lesson detail, which v2 does not report
2. **Assets & media** — v2 has no file upload
3. **Commerce** — offers, promo codes, purchases, training credits
4. **Learning paths** — paths, path items, path enrolments
5. **Events & webhooks** — subscriptions and payload previews
6. **Instructor-led training** — sessions, instructors, registrations
7. **Labels & tags**

Deliberately out of scope: catalog page-building, webhook *receiving*, caching, and cross-API
composite writes. Reasons are in the spec.

## Project documentation

| File | What it answers |
|---|---|
| [Design spec](docs/superpowers/specs/2026-08-26-csa-skilljar-design.md) | Architecture, routing rule, credential model, auth error taxonomy, phasing. **Start here.** |
| [ROADMAP.md](ROADMAP.md) | The block sequence — what ships in what order, and what is parked |
| [GOALS.md](GOALS.md) | What success looks like and how we would know it failed |
| [BUSINESS-CASE.md](BUSINESS-CASE.md) | Why CSA is investing, and the honest case that this project should shrink |
| [TODO.md](TODO.md) | Index of all open work |
| [DECISIONS-ADR.md](DECISIONS-ADR.md) | Technical decisions and why the rejected alternatives lost |
| [DECISIONS-PRD.md](DECISIONS-PRD.md) | Scope, audience, and what is deliberately out |
| [SECURITY-RESOURCES.md](SECURITY-RESOURCES.md) | Exposure surface, prompt-injection risk, credential custody |
| [DATA-RESOURCES.md](DATA-RESOURCES.md) | What data this handles, and what it deliberately never stores |
| [WAITING-FOR.md](WAITING-FOR.md) | External conditions we are waiting on, each with an observable trigger |
| [FRICTION.md](FRICTION.md) | Work that is harder than it should be — including how this project works with AI |
| [RACI.md](RACI.md) | Who decides what |
| [CLAUDE.md](CLAUDE.md) | Behavioural contract for AI agents working here |

## Development

**Always use a virtual environment.** The interpreter is pinned by `.python-version`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

.venv/bin/python -m pytest -q          # offline suite: no network, no credentials
.venv/bin/ruff check src tests scripts
.venv/bin/mypy

./scripts/verify.sh                    # or just this: everything CI checks
```

Commands are written `.venv/bin/...` deliberately — a bare `pytest` resolves to whatever
is on `PATH`, which is how a suite passes against the wrong dependency versions.

Contributions follow [CSA's public repo standards](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/PUBLIC-GITHUB-REPO-STANDARDS.md):
branch and PR for every change, required CI gates, no direct pushes to `main`.

## Licence

[Apache-2.0](LICENSE).

## Acknowledgements

Skilljar is a Gainsight product. This project is not affiliated with or endorsed by Skilljar or
Gainsight; it is an independent client built against their public APIs. The API snapshots in
`specs/` are fetched from Skilljar's published, publicly accessible OpenAPI documents.
