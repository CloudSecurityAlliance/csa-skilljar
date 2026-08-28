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

> **Status: Blocks 1–10. Full 73-tool parity, plus credential administration. v0.8.0 on PyPI.**
>
> **84 tools** over Skilljar's v2 API. Install from source until the first PyPI release:
> `pipx install git+https://github.com/CloudSecurityAlliance/csa-skilljar`
> | | |
> |---|---|
> | **Server** | `check_access` · `describe_capabilities` · `report_a_problem` |
> | **Courses** | `list_courses` · `get_course` · `create_courses` · `update_courses` |
> | **Lessons** | `list_lessons` · `get_lesson` · `create_lessons` · `update_lessons` |
> | **Quizzes** | `list_quizzes` · `get_quiz` · `create_quizzes` · `update_quizzes` · `delete_quizzes` |
> | **Questions** | `list_questions` · `get_question` · `create_questions` · `update_questions` · `delete_questions` |
> | **Question banks** | `list_question_banks` · `get_question_bank` · `create_question_banks` · `update_question_banks` · `delete_question_banks` |
> | **Bank bindings** | `list_quiz_question_bank_assignments` · `bind_quiz_question_banks` · `update_quiz_question_banks` · `unbind_quiz_question_banks` |
> | **Enrolment** | `list_enrollments` · `get_enrollment` · `update_enrollments` · `complete_enrollments` · `bulk_enroll_students` |
> | **Reporting** | `list_certificates` · `get_certificate` · `get_course_analytics` · `list_course_ratings` |
> | **Students** | `list_students` · `get_student` · `create_students` · `update_students` |
> | **Groups** | `list_groups` · `get_group` · `create_groups` · `update_groups` · `add_group_memberships` · `remove_group_memberships` |
> | **Signup fields** | `list_signup_field_values` · `get_signup_field_value` · `create_signup_field_values` · `update_signup_field_values` |
> | **Publishing** | `list_published_courses` · `get_published_course` · `publish_courses` · `update_published_courses` |
> | **Catalog** | `list_domains` · `get_domain` |
> | **Course visibility** | `list_visibility_overrides` · `add_visibility_overrides` · `remove_visibility_overrides` |
> | **Web packages** | `list_web_packages` · `get_web_package` · `create_web_packages` · `update_web_packages` |
> | **Students (destructive)** | `anonymize_student` · `deactivate_student` · `set_student_password` · `send_password_reset` — gated on `people.destructive`, which no profile but `full` grants |
> | **Groups (destructive)** | `delete_groups` — a hard delete that cascades to memberships and course visibility; gated on `groups.delete` |
> | **Publishing (public-facing)** | `unpublish_published_course` · `republish_published_course` · `delete_published_course` — gated on `publishing.write`, which `authoring` does not grant |
> | **Web packages (destructive)** | `delete_web_package` — refused while a live lesson uses the package |
> | **Credentials** | `register_oauth_client` · `list_oauth_clients` · `get_oauth_client` · `create_oauth_client` · `update_oauth_client` · `deactivate_oauth_client` · `rotate_oauth_client_secret` · `list_oauth_scopes` · `revoke_refresh_token` — all off unless the `admin` profile is named |
>
> All 73 official tools are present — asserted by `tests/test_parity.py`, not claimed. The three extra tools are our own server management. See [ROADMAP.md](ROADMAP.md).

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

### Connecting it to an MCP client

```bash
# Recommended: credentials stay in .env, and the client config holds no secret.
claude mcp add csa-skilljar -- /abs/path/to/csa-skilljar/scripts/mcp-launch.sh

# Or pass them directly - note this writes the literal secret into ~/.claude.json,
# which is not gitignored, and into your shell history.
claude mcp add csa-skilljar \
  -e CSA_SKILLJAR_V2_CLIENT_ID=... -e CSA_SKILLJAR_V2_CLIENT_SECRET=... \
  -- /abs/path/to/csa-skilljar/.venv/bin/csa-skilljar-mcp
```

`scripts/mcp-launch.sh` reads `CSA_SKILLJAR_*` variables from the repository's `.env`
(override with `CSA_SKILLJAR_ENV_FILE`) and execs the server. It parses the file rather
than sourcing it: `source` executes it, so a stray `echo` would print to stdout and
corrupt the JSON-RPC stream before the server ever starts.

Use an **absolute path** to the script or to `.venv/bin/csa-skilljar-mcp`. A bare
`csa-skilljar-mcp` resolves through `PATH`, which may find a different install.

Then call `check_access` first — it is built to work when nothing else does, and reports
which credentials resolved and which scopes the token carries.

**There is no login step and no browser.** The v2 credential is a machine credential: you create
an API client in the Skilljar Dashboard, put its id and secret in your MCP client's configuration,
and the server obtains its own access token on first use (`client_credentials`, ADR-003). No
redirect URI, no consent screen, no token file on disk. Skilljar's own hosted MCP server does use
an interactive flow — it is remote and acts for a browser user, which is exactly the constraint
running locally removes.

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

## Releasing

Publishing uses **PyPI Trusted Publishing** — GitHub Actions authenticates over OIDC and
proves its identity with the repository, workflow and environment it is running in.
**There is no API token anywhere**: not in the repository, not in a GitHub secret, not in
a `.pypirc`. Nothing to leak, rotate, or accidentally commit.

The identity PyPI checks is exactly this:

| Field | Value |
|---|---|
| PyPI project | `csa-skilljar` |
| Owner | `CloudSecurityAlliance` |
| Repository | `csa-skilljar` |
| Workflow | `release.yml` |
| Environment | `pypi` |

**One-time setup** (a person with the PyPI account, per `RACI.md` — credential and
publishing identity are not delegated): at
<https://pypi.org/manage/account/publishing/>, add a **pending publisher** with the five
values above. "Pending" is the form used when the project does not exist on PyPI yet; it
becomes a normal trusted publisher on first upload.

**Each release:**

```bash
# 1. Bump the single source of truth and refresh the editable install.
#    src/csa_skilljar/__init__.py  __version__ = "X.Y.Z"
.venv/bin/python -m pip install -e ".[dev]"
./scripts/verify.sh

# 2. Merge, then tag from main. The tag MUST equal the packaged version - the
#    workflow refuses to publish when they disagree, rather than shipping a
#    mislabelled artifact.
git tag vX.Y.Z && git push origin vX.Y.Z
gh release create vX.Y.Z --notes-from-tag
```

Publishing the GitHub release starts `release.yml`, which reruns the tests, `pip-audit`
and `bandit`, checks the tag against the packaged version, builds, and refuses to upload
an artifact containing anything matching `.env`, `token`, `secret`, `credential`,
`analysis/` or `docs-html/`, or missing `py.typed`.

It then waits: the `publish` job's `pypi` environment has a **required reviewer**, so the
upload does not happen until a human approves it in the Actions run.

The split into two jobs is deliberate. An environment gates a *whole* job, so a single
gated job asked for approval **before** any test ran. Now `build` does every check
ungated and uploads the artifact; `publish` downloads that exact artifact and does
nothing but upload it. The reviewer approves something already built and verified, and
`publish` has no build step that could produce something different.

Worth knowing that GitHub creates a missing environment *unprotected* on first use — so
`environment: pypi` in a workflow is a claim, not a control, until the environment
actually exists with rules on it.

## Licence

[Apache-2.0](LICENSE).

## Acknowledgements

Skilljar is a Gainsight product. This project is not affiliated with or endorsed by Skilljar or
Gainsight; it is an independent client built against their public APIs. The API snapshots in
`specs/` are fetched from Skilljar's published, publicly accessible OpenAPI documents.
