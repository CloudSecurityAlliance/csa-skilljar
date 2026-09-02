# DashboardBackend — covering what neither Skilljar API exposes

**Status:** design, not implemented.
**Date:** 2026-09-02
**Supersedes:** nothing. **Extends:** ADR-002 (routing), ADR-004 (tool naming).
**Prerequisite ADRs:** this design needs two new ones — see §11.

## 1. Purpose

Some work CSA staff do repeatedly exists **only** in the Skilljar dashboard. Grading is the
clearest case: a learner submits a free-form quiz response, Skilljar creates a task, and a
human scores it in the web UI. There is no API for it in either version, and none is planned
(§2). This design adds a third backend so those capabilities are reachable from the same tool
surface as everything else.

**Scope is set by frequency, not completeness.** Anything a human does in the dashboard
*repeatedly* is in scope. One-off administration — billing, organization settings, theming,
language setup, account deletion — is deliberately out (§3).

## 2. What was probed, and when

Everything below was verified against CSA's production organization on **2026-09-02**, not
read from documentation. Probe beats docs.

### 2.1 There is no grading API, and none is reserved

| Probe | Result |
|---|---|
| `task` in the v1 spec (160 paths) | one path: `/v1/webhooks/sample-dashboard-task-created` — the webhook *sample* |
| `task` in the v2 spec | none |
| `/v1/{tasks,dashboard-tasks,quiz-responses,quiz-attempts,quiz-submissions,grades,gradebook,quiz-grades,responses,submissions}` | **404** (control: `/v1/users` → 200, `/v1/nonexistent-xyz` → 404) |
| `/v2/{tasks,quiz-responses,quiz-attempts,quiz-submissions,grades}` | **404** (control: `/v2/courses/` → 200) |
| `/v1/tasks/{a real task id}` | 404 |
| Scope catalogue (88 advertised) | no `task`/`grading` scope. Nearest is `quizzes:read`/`quizzes:write` — quiz **definitions**, not responses |

The scope catalogue runs *ahead* of the API — 31 advertised areas have no endpoints — so its
silence here is meaningful. Grading is not merely unbuilt; it is unplanned.

**The v1 path shape has no trailing slash** (`/v1/users`, not `/v1/users/`). A first probe run
used trailing slashes, got ten clean 404s, and was worthless because its control 404'd too.
Recorded because the next person will make the same mistake.

### 2.2 The dashboard is backed by DataTables JSON endpoints

The list pages are not server-rendered tables to scrape. They are fed by JSON:

| Endpoint | `recordsTotal` | Columns |
|---|---|---|
| `/students/ajax` | 42,769 | `obfuscated_id, name, email, task_count, earliest_registration, latest_activity, available_actions` |
| `/tasks/ajax` | 661 | `type, submitted_at, completed_at, course, student_name, student_email` |
| `/groups/ajax` | 134 | `name, category, members, edit_members, edit_visibility, edit_managers, edit_training_credit_report, edit, delete` |
| `/course/ajax`, `/analytics/students/ajax`, `/analytics/enrollments/ajax` | — | return HTML, not this protocol |
| `/analytics/quizzes/ajax`, `/reports/orders/ajax`, `/audit-log/ajax` | — | 404 |

Parameters: `draw`, `start`, `length`, `skip_total_count`, `order[0][column]`,
`order[0][dir]`. `X-Requested-With` is **not** required. All 661 tasks came back in one
request with `length=1000`.

Every cell is `{display, sort, filter}`, where `display` is HTML. The task id is embedded in
the `type.display` anchor:

```
<a href="/tasks/grade-quiz/{task_id}?next=%2Ftasks%2F">Quiz Response</a>
```

`available_actions` is **structured, not markup**:

```json
{"options":[{"label":"Deactivate","custom_action":"deactivate-student","value":"{id}"}],
 "student":{"id":"{id}","name":"...","email":"..."}}
```

This matters for the whole design: **reads need no DOM scraping.** A page's HTML structure is
an implementation detail that changes with any redesign; this is a stable request/response
protocol with named fields.

### 2.3 Grading is an ordinary Django form POST

```
POST /tasks/grade-quiz/{task_id}
  csrfmiddlewaretoken                              (from the GET - see below)
  quiz_response_id
  question-response-{question_id}-correct          radio: correct | incorrect
  question-response-{question_id}-grader_feedback  textarea, optional
  email_student_on_completion                      checkbox
```

Three consequences:

- **It is not a score.** Binary correct/incorrect per question, plus an optional comment.
  No percentage, no partial credit. A tool called `submit_score` would misdescribe it.
- **Field names are semantic and id-bearing**, not generated CSS classes. A far better
  automation target than a React app; this is server-rendered Django, the same stack as v1.
- **Submitting can email a real learner.** `email_student_on_completion` is a form field.
- **The CSRF form token is not the CSRF cookie.** Measured: the `csrfmiddlewaretoken` value
  differs from the `sj_csrftoken` cookie, which is Django's masked-token behaviour. The token
  must be scraped from each `GET` of the grading page; reusing the cookie value will be
  rejected. This is the kind of detail that costs an afternoon if it is discovered during
  implementation instead of here.

### 2.4 Login is protected by hCaptcha; the rest of the app is not

`dashboard.skilljar.com/login` loads hCaptcha (two iframes, sitekey `3115eb7f…`). A scripted
login posts, receives `200`, and silently stays on the login page. Cookies present before
submit: `sj_csrftoken`, `__cf_bm`, `OptanonConsent`.

**We do not attempt to defeat it.** It is a bot-protection control on a third party's system.
The session must be established by a human, which is precisely what the control is for.

The session cookie is **httpOnly** — absent from `document.cookie`, which exposes only
`sj_dbu`, `sj_dbgid`, `sj_csrftoken`, `dashboardUiState` and analytics cookies. So it can be
captured only through the browser automation layer, never from page script.

### 2.5 The state of the task queue, as of this date

661 tasks: **631 completed, 30 pending.** Pending by submission year — 2022: 2, 2023: 6,
2024: 9, 2025: 12, 2026: 1. Completions by year: 2019: 1, 2020: 135, 2021: 55, 2022: 149,
2023: 94, 2024: 197, **2025: 0, 2026: 0**.

Nothing has been graded since 2024. Among the 30 outstanding are **three "Final Exam Part 2"**
and seven "CSA Authorized Instructor Agreement — Sign & Submit". This is an operations
finding, recorded here because it sizes the feature: the steady-state volume is tens to low
hundreds per year, not thousands. **This is not a bulk-clearing tool.**

## 3. Non-goals

Stated explicitly so they are decisions rather than omissions.

- **No general browser automation.** A fixed, small set of operations, each specified. Not
  "drive the dashboard".
- **No analytics.** Ten `/analytics/*` pages have no JSON endpoint and would require real DOM
  scraping. Highest cost, and the output is reports a human reads rather than repeated work.
- **No theming, languages, organization settings, billing, or account deletion.** One-offs by
  the frequency rule.
- **No automated login.** See §2.4.
- **No unattended operation.** The session is human-established and expires. A scheduled job
  that silently stops working is worse than one that never existed.
- **No grading judgement.** The server submits a decision it is given. It does not decide
  whether an answer is correct. See §7.3.

## 4. Architecture

### 4.1 The routing rule, extended

ADR-002 today: *v2 owns every capability v2 has; v1 is used only for capabilities v2 lacks.*

Extended, with the same absoluteness:

> **v2 → v1 → dashboard.** Each capability has exactly one owner, and the dashboard owns only
> what neither API exposes. A capability never moves *toward* the dashboard.

The dashboard tier is **first to be retired, not last**. If Skilljar ships a grading endpoint,
`grade_task` changes backend and keeps its name (ADR-004) — the same mechanism that will move
`list_assets` from v1 to v2.

### 4.2 It goes behind the same seam — the non-negotiable constraint

`DashboardBackend` methods are declared in `policy._GATES` exactly like v1 and v2 methods, and
the instance is wrapped by `PolicyBackend`. An undeclared method is **refused, not delegated**.

This is not tidiness. `describe_capabilities` can today honestly say "this install cannot do
X". A second route to Skilljar that does not consult the gate makes that sentence false, and
nothing outside the process can tell. A capability control that one code path ignores is worse
than no control, because it is believed.

### 4.3 No browser in the server process

The MCP server ships **no browser dependency**. At runtime `DashboardBackend` is an HTTP
client — `httpx` with a cookie jar — because §2.2 and §2.3 established that reads are JSON and
writes are form posts. Playwright is a **setup-time** tool, in an optional extra, used once to
capture a session a human established.

```
setup (human, occasional)      runtime (every call)
  playwright  ──► login ──►      httpx + session cookie
  human solves hCaptcha            GET  /tasks/ajax          (JSON)
  capture storage state            GET  /tasks/grade-quiz/id (CSRF token)
                                   POST /tasks/grade-quiz/id (form)
```

**Verified 2026-09-02.** This was the design's principal risk and it is resolved.

| Probe | Result |
|---|---|
| `urllib`, no cookie, bot-shaped UA, `/tasks/ajax` | `401` from **nginx**, no `cf-*` headers, no challenge page |
| `httpx` + `sj_sessionid`, `GET /tasks/ajax` | **`200 application/json`**, `recordsTotal=661`, all six columns |
| `httpx` + session, `GET /tasks/grade-quiz/{id}` | **`200`**, carrying `csrfmiddlewaretoken` (64 chars), `quiz_response_id`, the `question-response-*-correct` fields and `email_student_on_completion` |

Cloudflare's `__cf_bm` is set on the login page but does not gate the application paths: a
plain client with an obvious bot user-agent reached the app and was refused by the
application, not by an edge challenge. No browser is needed at runtime.

The session cookie is `sj_sessionid`, `httpOnly`, and stored encrypted in Chromium's cookie
database. It is recoverable only by letting a browser decrypt it, which is what the setup-time
capture does.

## 5. The session credential

The hardest part of this design, and the part most likely to be got wrong.

### 5.1 What it is

A dashboard session cookie is a **bearer credential with no scopes**. It can do everything the
logged-in human can. Unlike the v2 OAuth client — which carries 18 named scopes and is refused
locally before a request when one is missing — the session has no such structure to check.

Three consequences, each of which shapes a requirement below: it cannot be narrowed by
scope; it cannot be safely shared; and its blast radius on compromise is the whole
organization.

### 5.2 Requirements

1. **A dedicated dashboard user, never a personal staff account.** `/v2/roles/` returns 404
   but `roles:read`, `roles:write`, `admin-users:read`, `admin-users:write` are advertised
   scopes — so Skilljar has an admin-role concept in the dashboard today, even though the API
   cannot manage it. The session user gets the **minimum role that can grade**, established
   manually. Determining what that role is, is an open question (§11).
2. **Stored at `0600`, referenced by path, never inlined into an MCP registration.**
   `CSA_SKILLJAR_DASHBOARD_SESSION` names a file, the way `CSA_SKILLJAR_ENV_FILE` does. This
   matters concretely: `~/.claude.json` is mode 644 on a default macOS install.
3. **Never logged, never in a `__repr__`, never in an error message.** Existing repo rule.
4. **Expiry is a first-class state, not an error.** When the session lapses every dashboard
   tool must report *"the dashboard session has expired; re-run the capture"* — a setup
   instruction, not a stack trace. Same philosophy as the v2 credential messages.

### 5.3 The deviation this requires, stated rather than buried

`DATA-RESOURCES.md` says **no caching, no persistence**. A session file is persistence, and it
is persistence of a credential. It is a genuine departure and needs ADR-009 (§11), not a
footnote.

The compensating position: the alternative is a human solving a captcha before every operation,
which means the feature does not exist. The file holds no learner data, is `0600`, is
referenced by path, and expires on its own.

## 6. Capability gating

Two new capabilities. Neither is in `parity` — that profile mirrors the official Skilljar MCP
server, which has no dashboard tools, and adding to it would quietly change what the word means.

| Capability | Grants | In profiles |
|---|---|---|
| `tasks.read` | `list_tasks`, `get_task` | `people`, `reporting`, `full` |
| `tasks.grade` | `grade_task` | `full` only |

`tasks.grade` is `full`-only deliberately. It writes to a learner's record, can email them, and
on a certification path decides an outcome for a real person. It belongs with the other
consequential capabilities, not with routine authoring.

## 7. Tool surface

Three tools. Names carry no version and no "dashboard" marker (ADR-004).

### 7.1 `list_tasks`

Arguments: `filter_status` (`pending` | `completed` | `all`, default **`pending`**),
`filter_course_id`, `filter_student_email`, `page`, `page_size` (default 25, max 250).

Defaulting to `pending` is deliberate: the dashboard's own default shows all 661 with ungraded
sorted first, which reads as a 661-item backlog when it is 30. That misreading happened during
this design; the tool should not reproduce it. The response states both counts.

Returns per task: `id`, `type`, `submitted_at`, `completed_at`, `course_id`, `course_title`,
`lesson_id`, `lesson_title`, `student_id`, `student_email`. **Learner names follow the
projection rule under separate design** (`2026-09-01` name-blinding work, still open) — until
that lands, `list_tasks` withholds `student_name` and says so, because an unfiltered call
returns hundreds of real people.

### 7.2 `get_task`

Argument: `id`. Returns the task plus the questions awaiting grading — question text, the
learner's response, any uploaded file's name, and the quiz's `passing_percentage_correct`.
This is the tool that lets a human or a model *read* what needs grading.

**The learner's response is untrusted input.** It is free text submitted by a member of the
public, rendered to a model that holds an admin session. `SECURITY-RESOURCES.md` treats course
content this way already; this is the same class and higher stakes. The tool description must
say so, and the server `INSTRUCTIONS` block must repeat it.

### 7.3 `grade_task`

Arguments: `id`, `decisions` (list of `{question_id, correct: bool, feedback: str|None}`),
`email_student` (default **`False`**), `confirm` (required, must be `True`).

- **`confirm` is required** — the pattern already used by `anonymize_student` and
  `set_student_password`.
- **`email_student` defaults to `False`.** The dashboard checkbox defaults on; we invert it.
  Sending mail to a real person is a distinct decision from recording a grade.
- **Every question must have a decision.** A partial submission would silently mark the
  remainder incorrect. Refuse instead.
- **The tool does not decide correctness.** It submits decisions it is given. A model may
  propose them; the description must direct that the human confirms before the call, and
  `confirm` is where that lands.

## 8. Drift detection

The `/ajax` endpoints and the grading form are **undocumented and unversioned**. There is no
OpenAPI document to diff, so drift detection must be built rather than derived — the gap
`check_upstream.py` fills for the APIs.

`scripts/check_dashboard.py`, run on the same schedule, asserting:

1. `/tasks/ajax` returns JSON with the six expected column keys.
2. Each cell is `{display, sort, filter}`.
3. `type.display` still matches `/tasks/grade-quiz/([a-z0-9]+)`.
4. `GET /tasks/grade-quiz/{id}` still contains `csrfmiddlewaretoken`, `quiz_response_id`, and
   at least one `question-response-*-correct`.
5. The session is still valid — and reports *expired* distinctly from *changed*.

Any failure is loud. **Silence is not health**: a check that cannot distinguish "no drift" from
"could not reach the dashboard" would repeat the defect in issue #13, where a TLS timeout was
filed as drift for five days while real drift went unnoticed.

## 9. Error model

Reuses the existing taxonomy. Three dashboard-specific conditions map onto it:

| Condition | Raised as | Message says |
|---|---|---|
| No session file | `CredentialsMissing` | how to run the capture |
| Session expired | `CredentialsMissing` | re-run the capture; distinct from "not configured" |
| Response is HTML where JSON was expected | `UpstreamChanged` (new) | the dashboard changed shape; run `check_dashboard.py` |

The third is the ZD-2 case: an HTML body where JSON was expected usually means a redirect to
the login page. Parsing it as data would surface as an empty task list — the queue looking
clear when it is not.

## 10. Testing

`FakeDashboard`, alongside `FakeBackend` and `FakeV1Backend`, storing **raw `/ajax` payload
shapes** — `{display, sort, filter}` cells with HTML in `display`. Following the precedent that
`FakeBackend` stores webhooks *with* their secrets: a fake that pre-parsed would hide the whole
point of the parsing layer.

- Conformance: `DashboardBackend` and `FakeDashboard` satisfy one protocol.
- Gate: every `DashboardBackend` method appears in `_GATES`; an undeclared method is refused.
  Mutation-tested.
- `grade_task` refuses without `confirm`; refuses a partial decision set; sends
  `email_student_on_completion` only when asked. Each mutation-tested.
- Parsing: task id extracted from the anchor; a changed anchor shape raises rather than
  returning `None`.
- Integration (`CSA_SKILLJAR_INTEGRATION=1`): reads only. **`grade_task` is never exercised
  against production** until `WAITING-FOR-003` closes — the same rule as every other write, and
  it binds harder here because the side effect can be an email to a stranger.

Note the interaction with issue **#59**: the read-only integration guard does not currently run
in CI and its allowlist is 27 entries behind. Adding a backend whose write path emails people
before that guard works would be irresponsible. **#59 is a prerequisite, not a parallel task.**

## 11. Open questions

1. ~~Does a non-browser HTTP client work?~~ **Answered 2026-09-02: yes.** See §4.3.
2. **What is the minimum dashboard role that can grade?** The remaining blocker. Needs a human in the Skilljar
   dashboard. Determines whether §5.2.1 is achievable or whether the session is unavoidably
   full-admin — which would change the risk calculus enough to revisit this design.
3. **ADR-009 — persisting a session credential.** The `DATA-RESOURCES.md` deviation (§5.3).
4. **ADR-010 — the third routing tier.** ADR-002 is load-bearing and currently says two APIs.
5. **Should `grade_task` exist at all, or only `list_tasks`/`get_task`?** A notifier that
   surfaces the queue may capture most of the value at a fraction of the risk. The 30-item
   backlog suggests the bottleneck is *noticing*, not *submitting*.
6. Do the three ungraded "Final Exam Part 2" submissions represent people still waiting? Not a
   software question, but it is the reason this is worth building.

## 12. Retirement trigger

Add to `WAITING-FOR-001`: **if Skilljar ships a grading endpoint in v2, this backend retires.**
`check_upstream.py` already watches the path count and scope catalogue; add `assets`-style
watches for a `tasks` or `grading` scope appearing in the advertised list. Their appearance is
the signal, ahead of the endpoints.
