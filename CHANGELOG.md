# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.15.0] — 2026-08-31

### Fixed
- **`check_access` talked users out of the fix.** Its v1 detail said *"No v1-backed tools
  are implemented yet, so this is not currently needed"* — while **27** v1-backed tools
  were shipping. `_require_v1` correctly routes a user whose v1 tool just refused to call
  `check_access`, so the one message they were deliberately sent to was the one saying the
  credential was unnecessary. A silent gap would have been better; they would have kept
  looking. `--help` carried the same claim as `(no v1 tools yet)`.
- **A registry-derived guard so it cannot recur.** The new test enumerates the live tool
  registry, and fails if any registered tool requires `CSA_SKILLJAR_V1_API_KEY` while the
  guidance claims none do. Mutation-tested by restoring the original wording. The previous
  check (`scripts/check_docs.py`) could never have caught this: it ties *documentation* to
  artifacts, and the claim lived in a Python string.
- **`CSA_SKILLJAR_ENV_FILE` was set by the installers and ignored by the server.** Both
  `csa-skilljar-setup.sh` and `.ps1` write the credential to an owner-only file and point
  the registration at it by path. `mcp-launch.sh` honours that variable, but it is a repo
  script, is not shipped in the wheel, and is not what the installers register — they
  register the console script. So the file would be written, `chmod 0600`, announced as
  "Skilljar credential installed", and then ignored. It had not fired only because
  CSA-Plugins carries no credential yet. `env_with_file()` matches `mcp-launch.sh`'s
  contract exactly: an exported variable wins, the file is parsed and never sourced, and
  only `CSA_SKILLJAR_*` is taken from it — importing `PATH` or another service's key would
  be a privilege-escalation seam, not a convenience.

### Added
- **Guidance on how to obtain each credential**, which did not previously exist for v1 and
  was one vague line for v2. Both now name the Skilljar Dashboard.
- The v2 guidance names **scopes**, because that is the part people get wrong and the
  failure is confusing: this server checks scopes locally and refuses *before* calling, so
  an under-scoped client looks like an unsupported tool — and adding a scope needs the
  client re-issued, not a restart.
- **The server now says there is no sign-in**, in `check_access` and in the `INSTRUCTIONS`
  the model reads. Absence of a login is indistinguishable from a missing feature, and
  `csa-google-workspace` — installed on the same machines by the same script — does have
  an `authenticate` tool. Resolves FRICTION-004.

### Notes
- The v1 key is `CSA_SKILLJAR_V1_API_KEY`. Three documents named it
  `CINO_READ_ONLY_TESTING_KEY`, which nothing in the code has ever read.
- Recorded in the spec: Skilljar's own discovery document advertises only
  `authorization_code` and `refresh_token` and **does not list `client_credentials`**,
  which its token endpoint nevertheless accepts. The natural way to check whether this
  architecture is supported says no.

## [0.14.0] — 2026-08-30

### Added
- **`demonstration_plan` — the tour that is also the end-to-end test.** Follows the CINO
  pattern in `DEMO-AS-END-TO-END-TEST.md`, marked `[proven]`: built for
  `csa-google-workspace`, three runs, four real bugs, one of which had survived a fully
  green 660-test suite.
- **Two modes.** `read_only` changes nothing and is safe against the production
  organization these credentials reach. `read_write` also creates and deletes **content**
  — a course, a quiz, questions, a bank, an empty group — and never a learner, a
  publication or a credential. Every write step is paired with cleanup.
- It returns the **plan, not the result**; the model calls the tools. Running them inside
  the tool would block a conversation behind one call and demonstrate nothing — the tool
  would have done the work. It would also skip the thing no unit test reaches: whether the
  descriptions are good enough to use from a standing start.
- **Coverage is computed from the live registry**, not maintained, so a tool added next
  block shows up as a hole. Both modes reach zero gaps: all 112 tools are exercised,
  excluded with a written reason, or out-of-scope for the mode. That last category matters
  — counting write tools as "gaps" in `read_only` meant the number could never reach zero,
  so nobody would look at it.
- **Thirty-two tools are excluded on purpose and each says why:** irreversible PII
  erasure, credential minting, anything that emails a real person, and `get_purchase`,
  which has no listing endpoint so a demo has no id to use.
- Learner steps use **named accounts only** and every learner-facing listing carries a
  filter — `list_vilt_registrations` is pinned to one session, because unfiltered it
  returns hundreds of real names and email addresses.
- The plan asks for **two facts separately**: did anything error, and how many tools were
  exercised. A run that exercised nothing also produced no errors.

### Fixed
- The first live run found a gap **in the plan itself**: it predicted zero refusals and hit
  two, because it checked the capability profile and not the OAuth scopes — the policy
  allowed the calls and the scope pre-check stopped them. Prediction now covers both and
  says **which** refused, because a profile is changed with an environment variable and a
  restart while a scope needs the credential re-issued in the Dashboard.
- Two scanner-shaped detours, both fixed by restructuring rather than suppressing. The
  exclusion list is a **tuple of pairs** rather than a dict literal, because bandit reads a
  dict key containing "password", "secret" or "token" mapped to a string as a hardcoded
  credential and flagged four of these prose reasons. And the `nosec` guard in
  `test_zero_defect.py` now skips pure comment lines: it failed on its own explanatory
  prose, and bandit misread the same line as a suppression carrying five rule names. A
  guard that cannot tell a mention from a use is a guard that will be worked around.

### Notes
- Executed against live Skilljar: **52 of 61 steps ran, 2 errors**, both of them the scope
  pre-check refusing correctly and both now predicted up front.

## [0.13.0] — 2026-08-29

Released without a changelog entry at the time; written up here from the shipped commits.
Blocks 14 through 17 — learning paths, webhooks and event payloads, instructor-led
training, and taxonomy. 111 tools.

### Added
### Added
- **Block 14 — learning paths.** `list_paths`, `get_path`, `list_path_items`,
  `list_published_paths`, `list_course_series`, `list_learner_path_enrollments`. v2 has
  no path or series surface at all.
- The modelling is the substance: **three words that sound alike and are not.** A *path*
  is the sequence and is invisible on its own; a *published path* is that sequence on a
  domain, with a URL and visibility, and a path published to two domains is **two**
  published paths with separate settings; a *course series* is an unordered catalog
  grouping with no completion. Every description says which one it is and points at the
  others.
- `list_path_items` returns items in **path order with no rank field**, so the response
  order is the curriculum. The description says not to sort them, because a model that
  reorders alphabetically silently rewrites the sequence.
- `course_name_singular` / `course_name_plural` are surfaced because an organization may
  call its steps "modules" or "levels" — CSA's live data calls them "Courses", but using
  the API's word rather than the author's makes an answer read as someone else's product.
- `domain_name` is a **hostname, not an id**, and the error says so and points at v2's
  `list_domains`.
- Path enrolment is separate from enrolment in the courses inside a path — a learner can
  be enrolled in a path having started none of it.

### Fixed
- `V1_PAGE_NUMBER` in the pagination suite became a **dict of per-tool arguments**. A set
  was enough until three of these tools took a required identifier, at which point the
  "does it report a total" check would have failed for the wrong reason.

- **Block 15 — webhooks and event payloads.** `list_webhooks`, `get_webhook`,
  `preview_event_payload`.
- The compression first: v1 exposes a separate `sample-*` endpoint **per event type** —
  ten tools' worth of surface for one question, "what does a FOO event look like".
  `preview_event_payload` takes the event type and picks the endpoint, so the tool surface
  matches the question rather than the API. It accepts `COURSE_COMPLETION`,
  `course-completion` or `Course_Completion`, because the value appears in both spellings
  depending where you read it.
- **`/v1/webhooks` returns credentials in three places at once**, verified against CSA's
  production organization: `additional_headers` values (a 32-character `X-Skilljar-Secret`,
  in plaintext), an `auth` token in the `target_url` query string on two of three targets,
  and `basic_auth_password` on every row. These authenticate Skilljar **to** a receiving
  service, so passing them through would hand a model the shared secret that service uses
  to decide a request is genuinely from Skilljar.
- So the tools return **shape and never values**: header names, not header values; the
  URL's scheme, host and path, not its query string — but the query **parameter names**,
  because "the URL carries an auth parameter" is useful and its value is the credential.
  `basic_auth_password` is **replaced rather than omitted**, because omitting it silently
  reads as "no password is set", which is a different fact about the webhook. The
  withholding is stated, so nobody concludes there is no secret and goes hunting for a bug.
- Verified live: three secret values present in the raw backend response, **zero** in the
  tool output, for both the listing and the detail view. A test asserts the **fixture**
  still contains the secrets, so the leak checks cannot pass vacuously.
- Its own `events.read` capability rather than `content.read`: webhook configuration is
  where events go and how they authenticate, which is not a content question.

- **Block 16 — instructor-led training.** Two overlapping words: a **session** is the class
  — its name, instructor, capacity and joining details — and is **not a date**. A **session
  event** is a scheduled occurrence with a start, an end and a timezone, and is the thing a
  learner registers for. Any question with a date in it wants the second, so the first
  points there rather than answering badly.
- `list_vilt_registrations` returns a learner's **name and email on every row**, 341 of them
  in the reference org. It sits behind `people.read` with the other learner-reading tools,
  defaults to a small page, and an unfiltered call says so in its note — so a model narrows
  to one session instead of listing the organization and repeating hundreds of real contact
  details into a transcript.
- Registration and attendance are different facts: a session can be fully booked with half
  the room empty. Timezones are preserved and flagged, because the live data has sessions
  in `US/Pacific` and a time reported without one is wrong for most readers.

- **Block 17 — taxonomy.** Small, and entirely about a distinction the data cannot express.
  A label and a tag are both just a name; what differs is that **labels are internal** and
  never shown to learners, while **tags are public** and carry a slug used in catalogue
  URLs. Reporting one as the other misdescribes the catalogue in a way nothing in the
  response would reveal, so each description says which it is and points at the other.
  Group categories organise **groups** rather than content, so they are gated with
  `groups.read` — they are where `list_groups`' `filter_category_id` comes from.

### Notes
- `ilt-multi-session-events` is empty in the reference org and was skipped, per ADR-007's
  rule about ordering by evidence.
- Verified live: 103 sessions, 103 occurrences, 341 registrations with the unfiltered
  warning firing, 9 instructors, 50 labels, 17 tags, 7 categories, and the slug present on
  a tag and absent on a label.
- Two things the checks caught in Block 15: the sample-payload fake returned a bare object
  under `results` while the live endpoint returns a **list of one** — a double that accepted
  a shape the API never sends would have hidden a real rejection. And bandit flagged the
  withholding note itself, because the variable was called `_SECRET_NOTE`; renamed to
  `_WITHHELD_NOTE`, which removes the finding honestly rather than suppressing it.

## [0.12.0] — 2026-08-28

### Added
- **Block 13 — commerce, read-only.** `list_promo_codes`, `list_promo_code_pools`,
  `list_offers`, `list_training_credit_codes`, `get_purchase`. **v2 has no commerce
  surface at all**, so there is no routing question here.
- Read-only is a **decision, not a consequence of the write freeze** (ADR-007 calls this
  family read-biased). A promo code is money, a mistake is visible to customers, and the
  useful question is almost always "what exists and is it still valid" rather than "make
  more". A test asserts the module never grows a `create_`/`update_`/`delete_` tool.
- **Its own `commerce.read` capability, deliberately not in `parity`.** That profile
  mirrors the official server, which has no commerce tools — granting it there would
  quietly change what the word means. It sits in `reporting` and `full`.

### Fixed
- **Scale is the trap in this family, and the tools are shaped against it.** v1 defaults
  to 250 rows and honours `page_size=1000` — verified live. With 13,708 promo codes, a
  tool that inherited that default would put thousands of rows into a conversation to
  answer "are there any". These default to **25**, refuse above 250 with a message saying
  to read `total` instead, and always surface v1's count so "how many" is answerable from
  one small page.
- **The pagination test grew a third category.** v1 pages by NUMBER with a total; v2 by
  opaque cursor with none. The binary classification had no room for it — calling these
  "not paginated" would assert they take no paging arguments (false), and calling them
  cursor-paginated would demand a `page_cursor` they do not have. `V1_PAGE_NUMBER` now
  asserts what they actually do, including that they report a total.
- **`get_purchase` says there is no way to search.** v1 offers only the by-id route, so
  an id must come from a webhook payload or an order reference. Reporting "I could not
  find the purchase" would imply a search that does not exist.
- ADR-007's counts re-taken while building this: promo codes 13,687 → **13,708**, pools
  4,278 → **4,290** in two days. The ordering stands; the ADR now records that its
  numbers have a shelf life, and that "populated" and "reachable" are different questions
  — purchases are populated and unlistable.

## [0.11.0] — 2026-08-28

### Added
- **Block 12 — the asset library.** `list_assets` and `get_asset`: the files courses are
  built from. **v2 has no assets endpoint at all**, so this is the only way to resolve
  the `content_asset_id` that `list_lessons` returns.
- The ADR-002 split here is not the obvious one. v1 also has web-package endpoints, and
  they are **not** added: v2 owns list, get and delete (Block 9). Only
  `/v1/web-packages/{id}/lessons` is a v1-only capability there. Adding the rest "for
  completeness" would put one capability on two backends with two data shapes.

### Security
- **`get_asset` returns a credential-free download link, and that is a new egress path.**
  `download_url` is a presigned S3 URL: verified against the live API with a ranged GET
  carrying **no authorization header** — `206`, `application/pdf`. It works for about an
  hour, changes on every fetch, and needs no Skilljar credentials at all.
- So the URL is a **bearer capability, not a reference**: anyone who reads it can download
  the content, and none of this project's controls reach that far — not the capability
  profile, not the OAuth scope, not the v1 key. Recorded in `SECURITY-RESOURCES.md` as its
  own section and in the accepted-risk table, and in `DATA-RESOURCES.md`'s connections
  table, because it compounds the transcript problem already noted for demonstrations.
- Three things bound it: the **listing carries no link** (upstream's design, kept rather
  than smoothed over), the warning **travels in the payload** rather than only the
  docstring, and it **expires**. Nothing prevents a model repeating the URL, which is
  stated plainly rather than claimed as handled.
- `aspect_ratio` is deliberately **not** surfaced. It is `16:9` on all 157 assets in the
  reference org, PDFs included — a default, not a measurement, and returning it invites a
  model to report a document's aspect ratio as a fact about it.
- `type` is renamed to `asset_type` on the way out, because every v2 resource carries a
  JSON:API `type` and one word meaning two things across two backends is how a caller
  reads the wrong field.

## [0.10.0] — 2026-08-28

The second API. Skilljar has two, and until now this server spoke only to v2.

### Added
- **Block 11 — the v1 backend, and the first capability served by it.** `V1Backend` is a
  second API in every respect: HTTP Basic with the key as the **username** and an empty
  password, DRF envelopes, page-number pagination with a total, and `{"detail": …}`
  errors. Separate module, no fallback either way (ADR-002).
- `find_learner`, `list_learner_progress`, `get_learner_progress` — lesson counts against
  course totals, required-lesson counts, credits earned, latest activity, and
  re-enrolment history. v2's `EnrollmentAttributes` carries **none** of these, so "how
  far through is this learner, in lessons" is answerable only through v1. A test asserts
  that claim against the v2 spec, so if v2 ever grows the fields, ADR-002 says the
  capability moves and the test says so first.
- **ADR-002 is now a passing test.** `test_no_capability_is_served_by_both_backends`
  asserts the two backends' method sets are disjoint; a capability answered by both would
  return a JSON:API shape or a DRF shape depending on which replied.
- One `_GATES` table covers both APIs, so a capability cannot be gated in one and open in
  the other. The v1 backend is policy-wrapped with the same policy.
- The v1 key is optional. Without it the v1-only tools raise a typed error naming the
  variable and stating it is a **separate credential** from the v2 client — the likeliest
  confusion — while the whole v2 surface keeps working.

### Fixed
- **Two upstream behaviours found by probing, neither in Skilljar's published v1
  document.** First: **per-lesson progress does not exist.** The documented endpoint
  returns 404 on the live API — verified by walking the prefix, with 401/404 controls
  proving the key was not the problem. Every alternative route 404s too. No tool claims
  to provide it, and both progress tools say "COUNTS ONLY, NOT WHICH LESSONS" so a model
  cannot report the counts as per-lesson detail.
- Second: **the by-id fetch resolves by the underlying course, not the publication.** A
  course published to two domains returns the wrong one with a `200` and no indication
  anything was substituted — 53 of 54 enrolments matched, which is what made it
  dangerous. `get_learner_progress` selects from the unpaginated listing instead: same
  single request, cannot return the wrong publication.
- **v1 answers in two envelope shapes** — the DRF envelope and a bare JSON array — and a
  reader assuming one silently returns nothing for the other. `parse_page` normalises
  both plus the single-object form, and `FakeV1Backend` stores the **raw** shapes so the
  double exercises the same normalisation rather than teaching a lesson the API does not.
- The README still said "install from source until the first PyPI release". 0.9.0 has
  been on PyPI since this morning.

### Fixed
- **The release artifact guard refused a real release.** It matched the substring
  `"credential"` against every filename, so Block 10's `_tools/credentials.py` — a module
  named after the domain it implements — looked like a credential file, and v0.9.0's
  build failed. The rule now matches what a file **is**, not what it is called: a
  credential arrives as a `.env`, a `.pem`, a `client_secret.json`, not as a Python
  module whose subject is credentials.
- The guard also lived as a heredoc inside `release.yml`, so it ran **once per release
  and nothing could test it** — its first real firing was the false positive above. It is
  now `scripts/check_artifact.py`, run by `scripts/verify.sh` whenever a `dist/` exists
  and exercised by `tests/test_artifact_guard.py` with deliberately bad archives: real
  secret files, repository furniture, a missing `py.typed`, an empty archive, and the
  sdist `pkg-version/` prefix that would otherwise hide a directory exclusion.
- Added the case that would let an empty release through: no distributions found at all
  now fails, rather than passing every "nothing bad is present" rule vacuously.

## [0.9.0] — 2026-08-28

Credential administration, and the release process fix that this version is the first to
use.

### Added
- **Block 10 — credential administration. The first work past parity.** Eight tools, and
  the asymmetry they close is the point: Skilljar's own MCP server ships the tool that
  **mints** a credential and withholds every tool that **audits or remediates** one.
  Through it you can create an OAuth client and then cannot list what exists, see what a
  client may do, narrow it, rotate a leaked secret, or turn it off.
- `list_oauth_clients`, `get_oauth_client`, `list_oauth_scopes`, `create_oauth_client`,
  `update_oauth_client`, `deactivate_oauth_client`, `rotate_oauth_client_secret`,
  `revoke_refresh_token` — all gated by `admin.credentials`, **including the reads**.
  Enumerating an organization's credentials is the reconnaissance step, so
  `list_oauth_clients` is gated exactly as hard as rotation.
- `create_oauth_client` states at length that it is **not** `register_oauth_client`: this
  one is authenticated and **bound to the organization**, while the official server's
  dynamic-registration tool binds none — its client authenticates fine and then reads
  nothing, forever, with no error that says why. Two ways to create a credential, one of
  which silently does not work, is the trap most worth a long description.
- `revoke_refresh_token` reports that revocation was **requested**, never confirmed. RFC
  7009 §2.2 requires the endpoint to answer success whether or not the token existed, so
  a typo and a real revocation are indistinguishable. Verified live against a deliberately
  invalid token: `200`, empty body, no `Authorization` header needed.
- It is the **second unauthenticated call**. `_register` became `_unauthenticated()`,
  shared with `register_oauth_client`, and the guard that enumerates the backend now
  asserts the two paths **by name** rather than by count — `len(callers) == 2` would pass
  if registration were swapped for something else entirely.
- `deactivate_oauth_client` is named for what it does. Skilljar's endpoint is a `DELETE`
  verb whose own summary reads "Deactivate client": the record survives with `is_active`
  false, and the description says not to report it as deleted.
- `rotate_oauth_client_secret` warns that the old secret dies **immediately**, so
  everything still using it breaks the moment the call returns.

### Fixed
- **The release approval came before the tests.** `release.yml` was one job gated by the
  `pypi` environment, and an environment gates a *whole* job — so a reviewer was asked to
  approve a publish before a single test had run, then waited to find out whether it
  passed. An approval that cannot be informed by the checks is a button, not a control.
  Split into `build` (every check, ungated) and `publish` (upload only, gated), passing
  the artifact between them. The reviewer now approves an artifact that is already built,
  tested, audited and content-checked — and `publish` has no build step, so it cannot
  produce something different from what passed.
- Two brittle literal counts became derived. `tests/e2e` asserted "76 tools" and the
  parity test lumped every addition into one "server management" set. The first turns
  each block into an edit that teaches nothing; the second would have quietly
  reclassified eight API tools as not touching an API. Beyond-parity tools are now their
  own register, and a test asserts each is admin-gated so a future one cannot arrive
  ungated by omission.

## [0.8.0] — 2026-08-27

**First release. Full parity with Skilljar's official MCP server — all 73 of its tools,
asserted by `tests/test_parity.py` rather than claimed — plus pagination on every listing
that supports it, capability gating, and a local scope pre-check.**

Collapses the six versions the roadmap had assigned to Blocks 2–9 (v0.1.0–v0.8.0) into
one, because none of them was ever published: the release was blocked on a v2 credential
(`WAITING-FOR-002`, closed 2026-08-27) while the blocks landed behind it. The number is
the one the roadmap gave to parity-complete, which is the honest description of what this
is — a working, complete, pre-1.0 surface.

**Writes are implemented but unproven against Skilljar.** No write tool has ever run
against a real organization, and `tests/integration/` is enforced read-only until
`WAITING-FOR-003` closes. That blocks confidence, not delivery, and is stated here so the
absence is not mistaken for an absence of testing.

What follows is the per-block detail, newest first.


### Fixed
- **Five list tools never paginated.** `list_groups`, `list_visibility_overrides`,
  `list_signup_field_values`, `list_published_courses` and `list_domains` read `has_more`
  and `next_cursor` out of `meta`. Real Skilljar — and `FakeBackend`, which matches it —
  put both at the **top level** of the envelope; `meta` carries only `page_size`. So all
  five always reported `has_more: false` and never emitted a cursor: a caller was told
  "that is everything" after one page. Confirmed against live Skilljar, where
  `list_domains` returned one row and claimed there were no more.
- Introduced in Blocks 7–9. The eight earlier list tools read the envelope correctly,
  which is why it looked like a working pattern.
- **Nothing caught it because the per-block tests asserted `has_more is False` on
  single-page fixtures** — an assertion that passes whether the code works or not. A test
  that can only observe the value the bug produces is not a test of it.

### Added
- **`tests/test_pagination.py`** — one fixture deep enough to force a second page, driven
  through the real tools, for every paginated tool at once: first page reports more and
  offers a cursor, the cursor advances, the last page says so. Plus the inverse for the
  three tools Skilljar does not paginate, which must not grow paging arguments they
  cannot honour.
- It is **fail-closed**: a list tool that appears in neither the paginated nor the
  unpaginated set fails the classification test, so the next one is covered without
  anyone remembering.

### Added
- **The integration suite can no longer write to a real organization.** Its conftest
  claimed "everything here is READ-ONLY" for several blocks and nothing enforced it —
  the suite was read-only by habit, and a habit is not a control. `live_client` is now
  wrapped in `ReadOnlyClient`, which is **fail-closed**: a method absent from a
  hand-written allowlist raises before anything reaches the network, so a tool added
  next block is refused by default.
- The allowlist is hand-written rather than derived from `policy._GATES`, and two tests
  assert the two AGREE without either being built from the other. Deriving it would make
  the control agree with a mislabelled gate instead of checking it.
- Verified by adding a rogue test calling `create_courses` against live Skilljar and
  watching it refuse; and by three mutations — unwrapping the fixture, and sneaking a
  write method onto the allowlist, both caught.
- **`WAITING-FOR-003`** records the open question behind this: where may this project
  write? The only organization these credentials reach is CSA's production one, with
  42,669 real learners. It carries the questions for Hannah and notes that the dev
  client still holds four authoring write scopes that nothing currently needs.

### Added
- **`scripts/mcp-launch.sh`** — reads `CSA_SKILLJAR_*` from a `.env` file and execs the
  server, so an MCP client can be pointed at it and the client configuration holds no
  secret. `claude mcp add -e KEY=value` writes the literal value into `~/.claude.json`,
  which is neither gitignored nor a secrets store, and puts it in shell history on the
  way.
- It **parses** the file rather than sourcing it. `source` executes the file: a stray
  `echo` in `.env` would print to stdout and corrupt the JSON-RPC stream before the
  server started, and any other command in it would simply run. Both are regression
  tests, and reverting to `source` kills three of them.
- Only `CSA_SKILLJAR_*` names are exported — this repository's own `.env` also holds a
  v1 testing key that is not the server's to receive — and an already-exported variable
  wins over the file, so a one-off override needs no edit to the credential file.

### Fixed
- **The scope pre-check refused every call against a real token.** Skilljar issues
  granted scopes in a **`scopes`** claim holding a JSON **list**; this code read the
  RFC 6749 / RFC 9068 standard `scope`, a space-delimited string. So `granted_scopes()`
  returned empty for every production token, and every scoped v2 call was refused with
  "Your v2 client was issued: (none). Re-issue it including `courses:read`" — against a
  client that had been issued seventeen scopes correctly. Both claim names and both
  shapes are now read.
- The offline suite was green throughout, because its JWT fixture could only produce
  `scope` as a string — the shape the code already expected. **A fixture that can only
  express your own assumption cannot catch a mismatch with the vendor.** The helper now
  takes arbitrary claims, and the vendor's real shape is recorded next to the tests.
- **"No scope claim" and "no scopes" are now different answers.** `granted_scopes()`
  returns `None` when the token does not declare its scopes, and `()` only when it
  declares none. Collapsing them meant an unrecognised claim silently refused everything
  and blamed the credential — the same absorbing-state shape as the `_expired` bug in
  ZERO-DEFECT §17. `check_access` reports `scopes_unknown` rather than an empty list.

### Fixed
- **ADR-003 cited evidence that does not hold.** It said the API's authorization server
  "does offer `client_credentials`". It does not advertise it — `grant_types_supported`
  lists only `authorization_code` and `refresh_token`, the same as the hosted MCP
  server's. The decision is still correct, but the evidence is now a probe: the token
  endpoint returns `401 invalid_client` for `client_credentials` with fake credentials
  (the grant was accepted and reached the credential check), while a nonsense grant type
  returns `400 invalid_request` and the validator names `client_credentials` first among
  the three it accepts. An ADR whose stated reasoning fails when checked is worse than
  one that says less.
- This is the mirror image of the discrepancy already recorded in `CLAUDE.md` — 88
  scopes advertised against 28 implemented. There the vendor's metadata runs ahead of
  the API; here it runs behind. Probe beats docs in both directions, the vendor's own
  machine-readable docs included.

### Added
- `scripts/check_upstream.py` now probes the `client_credentials` grant on every drift
  check. It needs no credentials — `401 invalid_client` and `400 invalid_request`
  separate "grant accepted" from "grant withdrawn" — and if Skilljar ever withdraws it,
  this server cannot authenticate at all, since there is no browser here to run
  `authorization_code` through.

### Fixed
- **`serverInfo.version` was an empty string** in the MCP initialize handshake — the
  field a client shows when someone asks which build they are talking to. `MCPServer`
  was constructed without `version`. No in-process test reads the handshake, so nothing
  caught it until a stdio smoke test looked.

### Added
- **`tests/e2e/` — the first tests that drive the installed console script as a
  subprocess over stdio**, the way a real MCP client does. Everything else builds the
  server in-process, which cannot see the initialize handshake, what reaches stdout, or
  whether the console script is wired up at all. Three real defects have hidden in that
  gap.
- The stdout-purity check (CLAUDE.md invariant 1) runs in the fixture teardown, so every
  e2e test asserts it regardless of what it was written to exercise. Getting it to work
  took three attempts, each failing silently:
  1. Reading stdout only up to the last response missed a stray `print()`, because
     `print()` to a pipe is BLOCK-buffered and the bytes sit in the buffer past every
     response the test read.
  2. Reading the buffer at exit still missed it, because `terminate()` sends SIGTERM and
     tears the process down WITHOUT flushing. The test now closes stdin and waits for a
     graceful exit, which is what flushes.
  3. `shutil.which` resolved the console script through PATH and found a **stale pipx
     install from an earlier release** — eight tools missing, wrong version, every
     assertion reporting on software that is not this checkout. The script is now
     resolved next to the test interpreter, and one test asserts the subprocess imports
     `csa_skilljar` from this repository.
- A missing console script is a loud collection error rather than a quiet skip, because
  any editable or wheel install provides it and a suite that skips itself reports green
  while testing nothing (ZD-17). `CSA_SKILLJAR_NO_E2E=1` opts out deliberately.

### Added
- **Block 9 — web packages and client registration. PARITY COMPLETE.** Six tools, and
  the last of the official server's 73. `tests/test_parity.py` now asserts the diff:
  73 of 73 present, zero missing, three declared extras of our own.
- Web packages are the only ASYNCHRONOUS family. `create_web_packages` queues an
  outbound fetch and returns rows in state PROCESSING; a malformed archive surfaces
  later as state ERROR and never as a failure on the create call. The description says
  so explicitly, because a model that reports "uploaded" here is reporting on a job that
  has not run.
- `create_web_packages` deliberately does NOT deduplicate on `content_url` — every other
  create tool here does, and two identical URLs are a legitimate request for two
  packages.
- `update_web_packages` refuses `type`, `state`, `base_path` and `display_name`. Skilljar
  accepts them and silently ignores them, which is unusual for this API and exactly
  ADR-008's case.
- `update_web_packages` warns that a rename can look like it did nothing: `display_name`
  is derived and only tracks `title` once the package reaches READY.
- `delete_web_package` takes one id rather than a batch, because its conflict outcome
  has no home in a per-row result: deleting a package a live lesson still uses is
  refused outright.
- `register_oauth_client` is the only UNAUTHENTICATED call in the server and the only one
  that returns a credential. It is routed through a dedicated `_register` path rather
  than `_send`, so the organization's bearer token is never sent to a registration
  endpoint that does not want it — and so the call works when no credential is
  configured, which is the situation someone registering a client is in. RFC 7591's
  `{error, error_description}` shape is surfaced rather than collapsed to a status code.
  It is off unless the `admin` profile is named, though Skilljar's own server ships it
  enabled.
- New `webpackages.read` / `webpackages.write` capabilities; the `authoring` profile
  grants both, since packages are authoring material.

### Fixed
- `get_certificate` returned only status and timestamps, dropping `code` — the public
  verification code, which is the thing a learner or employer actually quotes — and
  `score_as_percent`. Both are now returned, and the description explains that a null
  score means "not recorded", not zero. Found by the new parity test's
  minimum-description check rather than by anyone reading it.
- **`scripts/verify.sh` was weaker than CI.** CI runs `bandit` and `pip-audit` in a
  `security` job; verify did not, so the pre-commit gate passed green while CI failed —
  the same class of problem the script was written to prevent. Both now run locally, and
  both tools moved into the `dev` extra so CI and verify use the same versions. Verified
  by reintroducing a finding and watching verify fail.
- Three `bandit` B105/B107 `hardcoded_password` hits, all name-heuristic false positives
  on RFC 7591 vocabulary. One was fixed honestly by renaming `_SECRET_WARNING` to
  `_SHOWN_ONCE_WARNING`; the other two are annotated, because `token_endpoint_auth_method`
  is Skilljar's own parameter name and ADR-006 forbids renaming it. Recorded in
  `SECURITY-RESOURCES.md` with counter-evidence tests, including one that refuses a bare
  `# nosec` anywhere in `src`.
- A new `ConflictError` would have reached the MCP client as `UnexpectedToolError` with
  its **message discarded** (CLAUDE.md invariant 2). Added its translation clause, a
  base-class backstop so a future subclass degrades to readable rather than silent, and
  `tests/test_error_translation.py`, which walks `SkilljarError.__subclasses__()` so a
  new error type is covered the moment it is defined.

### Added
- **Block 8 — publishing and catalog.** Twelve tools, and the first whose effects are
  visible to the anonymous public: publishing puts a course on a customer-facing domain,
  `open_access` allows anonymous access, and `visible_on_catalog` lists it publicly.
- A new `publishing.read` / `publishing.write` capability pair. `publishing.write` is in
  no profile but `full` — notably not in `authoring`, so a credential that can write
  lesson HTML cannot ship it to the internet.
- The three visibility-override tools are gated by `groups.*`, not `publishing.*`.
  Upstream hangs them off `/v2/groups/{id}/relationships/published-course-visibility/`
  and requires `student-groups:write`; gating by the scope the credential actually needs
  keeps the local gate and the remote one in agreement.
- `update_published_courses` refuses `slug`, `course_id` and `domain_id` rather than
  passing them on. Skilljar accepts all three and silently ignores them, which is
  exactly the case ADR-008 exists for.
- `unpublish_published_course` frees the slug and `republish_published_course`
  reassigns it, so a course can return at a different public URL. Both descriptions say
  so, and a regression test asserts the slug can change across the cycle.
- `delete_published_course` is documented as what it is — a soft unpublish, near-identical
  to `unpublish_published_course`, named after v1's DELETE verb rather than its effect.
  Each tool points at the other so a model is not left guessing which was meant.
- `add_visibility_overrides` documents that the unique key includes `is_visible`, so an
  allow row and a block row for the same course coexist rather than replacing each other.
- `remove_visibility_overrides` echoes the request's `published_course_id` rather than
  the override's own id, reproducing upstream's deliberate choice so results correlate to
  inputs without a second lookup.
- `publish_courses` documents the two booleans that default TRUE
  (`require_all_prerequisites`, `unique_progress_per_enrollment`) against ten that
  default false, and that a duplicate publish is a per-item conflict rather than a
  batch failure.

### Added
- **Block 7 — groups and signup fields.** Eleven tools. Groups decide which published
  courses a learner can see, so they are administered like content but grant access like
  people; they get their own `groups.read` / `groups.write` / `groups.delete`
  capabilities rather than borrowing either family's.
- `delete_groups` is gated by `groups.delete` alone, in no profile but `full`. A group is
  a **hard** delete — not a soft one like quizzes and banks — and its memberships and
  published-course visibility overrides cascade at the database, so deleting a group can
  revoke course access learners currently have.
- `update_groups` distinguishes an **absent** `category_id` from an **explicitly null**
  one: null clears the category, omitted leaves it alone. `rule_email_domains` replaces
  the stored array rather than merging, and the description says so, because the natural
  assumption silently deletes the caller's other domain rules.
- Group membership tools are annotated idempotent, which they genuinely are: adding an
  existing member succeeds and removing a non-member reports `deleted`. The result
  therefore cannot be used to test membership, and the tools say so rather than implying
  a change occurred.
- `create_signup_field_values` is an upsert wearing a `create_` name, with a hybrid
  envelope — `student_id` at the top level, per-field items in the batch. It keys items
  by the signup-**field** id while `update_signup_field_values` keys them by the
  signup-field-**value** id; both descriptions name the other call's identifier so a
  model holding one id can tell which it has.
- `get_signup_field_value` takes `signup_field_value_id`, not `id`. Every other
  single-object lookup takes `id`; this one matches Skilljar's parameter exactly, per
  ADR-006.
- Signup-field values are learner-typed free text and are labelled untrusted, the same
  treatment `list_course_ratings` and lesson HTML get.

### Fixed
- **ROADMAP's `updated_at` note was half the story.** It named `GroupAttributes` as the
  lone v2 resource spelling the timestamp `updated_at`. A survey of all fourteen
  `*Attributes` schemas found two: `GroupAttributes` and `VisibilityOverrideAttributes`,
  the latter a Block 8 tool. Corrected in place so Block 8 is not misled.
- ROADMAP listed the Block 6 tool as `set_password`; the captured registry says
  `set_student_password`. The code was built from the registry and was already correct.

### Added
- **Block 6 — students.** Eight tools, and the ones this project was most careful about:
  irreversible PII erasure, deactivation, and two password paths.
- A new `people.destructive` capability holding all four sensitive tools. It is granted by
  **no named profile except `full`** — the `people` profile, which an operator setting up
  learner administration would reach for, gives `people.read` and `people.write` and cannot
  touch erasure or passwords.
- `anonymize_student` and `set_student_password` refuse to run without `confirm=True`. This
  is a restatement gate, not an access control: it makes a destructive call legible to a
  human reading the transcript. The capability gate and the OAuth scope are the real
  controls.
- `anonymize_student` is the only call in the codebase that sends Skilljar's
  `X-Confirm-Destructive` header, and a test enumerates every other call to prove it.
- `update_students` refuses `is_inactive: false` combined with other fields, because
  Skilljar accepts that and silently drops the other fields. Reactivation takes two calls.

### Added
- **Block 5 — enrolment and reporting.** Nine tools, and the first that affect people
  rather than content. Both writes are gated on `enrolment.write`, which the `authoring`
  profile does not grant.
- `complete_enrollments` requires `send_notifications` with no default, because it decides
  whether real learners receive email.
- `list_course_ratings` returns learner-written free text and says so — the same
  attacker-influencable surface as lesson HTML.

### Added
- **Block 4 — question banks and bindings.** Nine tools. Reusable exam item pools, and
  the quiz-to-bank binding that makes them reusable — neither of which v1 can do.
- Re-binding an already-attached bank is an idempotent **partial** update: omitted fields
  keep their stored values and an omitted `order` is not re-derived.
- `delete_question_banks` states in its description that deleting a bank silently unbinds
  every quiz using it, while leaving those quizzes alive.

### Added
- **Block 3 — quizzes and questions.** Ten tools, and the project's first destructive
  operations (`delete_quizzes`, `delete_questions`).
- A new `content.delete` capability, deliberately separate from `content.write`: an
  authoring credential that can create and update content cannot destroy it. Off in every
  profile except `full`.
- Local encoding of the question quiz-XOR-bank rule, the per-type answer-shape rules, and
  the fields the service assigns rather than accepts.
- Documented behaviour that exists only in the captured registry: `FILL_IN_THE_BLANK`
  forces every answer correct, answers are immutable on update, and deleting a quiz spares
  bank-owned questions.

### Added
- **Block 2 — courses and lessons.** Seven new tools: `get_course`, `create_courses`,
  `update_courses`, `list_lessons`, `get_lesson`, `create_lessons`, `update_lessons`.
- Batch writes over v2's `207` envelope, with per-item results preserved rather than
  collapsed into one status.
- Local validation that mirrors the API's document-level `422`: an invalid item rejects
  the whole call rather than writing part of it.
- The lesson type XOR rules (`HTML`/`MODULAR`/`QUIZ`), and a confirmation flag guarding
  the `content_items` tri-state where an empty list deletes every child.
- `tests/integration/` — the first live-Skilljar suite, gated on
  `CSA_SKILLJAR_INTEGRATION=1`, with a guard asserting the gate skips *for the right
  reason*.
- ADR-008: reject read-only fields the official server silently ignores.

### Added (Block 1)
- **Block 1 — a working server.** A local stdio MCP server over Skilljar's v2 API with four
  tools: `check_access` (which credentials work and what each unlocks),
  `describe_capabilities` (what exists but is not enabled), `report_a_problem` (a filable
  report carrying no ids and no credentials) and `list_courses` (one real read).
- `SkilljarClient` library with a `Backend` protocol seam, `V2Backend`, `FakeBackend`, and a
  conformance guard comparing all implementations signature-for-signature.
- Fail-closed `PolicyBackend`: a backend method with no declared gate is refused, not
  delegated. Named profiles (`parity` default, through `full`).
- OAuth `client_credentials` authentication with a local scope pre-check — an impossible call
  is refused by name, with no network traffic, using a scope table generated from the v2
  OpenAPI spec.
- `scripts/verify.sh`, `scripts/check_docs.py` (25 documentation claims asserted against the
  artifacts) and `scripts/gen_scopes.py`.
- Design spec: `docs/superpowers/specs/2026-08-26-csa-skilljar-design.md`.
- Upstream API snapshots in `specs/` — Skilljar v1 (OpenAPI 3.0.3) and v2 (OpenAPI 3.1.0),
  fetched 2026-08-26.
- Surface analysis in `analysis/` — a 66-entity reconciliation of both APIs, plus the
  live OAuth scope catalog.

119 tests, 96% coverage, offline with no network and no credentials.
