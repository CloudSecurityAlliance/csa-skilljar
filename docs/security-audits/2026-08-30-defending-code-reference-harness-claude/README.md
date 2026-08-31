---
audit_id: 2026-08-30-01
date_started: 2026-08-30T01:03Z
date_completed: 2026-08-31T17:10Z
target: csa-skilljar
target_commit: 280c8e8                   # pinned detached worktree; the tree could not move under the audit
target_version: 0.13.0
main_at_record_commit: ed97ee3           # main moved after the swarm; the worktree stayed pinned
commits_landed_during_audit: 2           # 6c74ff8, ed97ee3 — neither touched a cited file except a version bump

tool: claude-code
tool_harness: anthropics/defending-code-reference-harness
tool_workflow: "/threat-model bootstrap, then manual adversarial review"
model: claude-opus-5
subagents: "7 parallel research agents, same model (docs, surface, credential/infra, asset, history, advisory, tests)"

human_interaction: heavy
automation: assisted
review_depth: adversarial

scope_covered:
  - "ALL of src/csa_skilljar/ — 38 files, ~10,200 lines, static read"
  - "All 112 MCP tools across 23 families, enumerated individually with annotation and capability"
  - "policy.py, scopes.py, auth.py, client.py, backend.py, v1backend.py — the gating and credential path"
  - "tests/ AS CODE — 56 files, ~8,100 lines, including tests/integration/ and the read-only guard"
  - ".github/ (4 workflows), .githooks/, scripts/ (6 scripts), packaging, .gitignore, secret hygiene"
  - "docs/ (12 files, ~5,200 lines), DECISIONS-ADR/, DECISIONS-PRD/, FRICTION/, analysis/, root Markdown"
  - "git history — 130 commits across all refs, security-keyword mined"
  - "GitHub Advisory DB via gh — repository plus 14 declared packages and 12 transitive candidates"
scope_excluded:
  - "No target code was executed. No pytest, no scripts, no console entry point."
  - "No call against api.skilljar.com. No credential was read. The integration suite was read, never run."
  - "Skilljar's own rendering of content_html was NOT tested — this is T1's load-bearing assumption and the audit says so rather than guessing."
  - "No dynamic testing, fuzzing, or running-agent prompt-injection exercise."
  - "OSV.dev, NVD and the PyPA advisory database were NOT queried — GitHub Advisory DB only."
  - "build/ and docs-html/ were inventoried and read but not treated as authored source."
inputs:
  - "SECURITY.md, SECURITY-RESOURCES.md, DATA-RESOURCES.md, DATA-NEEDS.md, RACI.md"
  - "CHANGELOG.md, TODO.md, GOALS.md, BUSINESS-CASE.md, API design spec, all ADRs and PRDs, FRICTION/"
  - "CLAUDE.md, CHATGPT.md, GEMINI.md (the agent contracts)"
  - "MCP specification tool-annotation semantics"
  - "Owner corrections, 2026-08-30 and 2026-08-31 (recorded in §6)"

findings_total: 37
findings_exploitable: 2
findings_conditional: 1
findings_hardening: 13
findings_informational: 22

remediation_status: deferred-by-design
remediation_context: "separate session — see Handoff"
remediation_record: null
supersedes: null
---

# Threat model and code review, 2026-08-30

## 1. Summary

This audit produced a 37-threat model across 20 entry points for `csa-skilljar`
at `280c8e8` (v0.13.0) — a local stdio MCP server exposing **112 tools** over
both of Skilljar's REST APIs, holding two independent credentials, and reaching
**42,669 real learner records**. It is the second audit run with this harness;
the first covered `csa-google-workspace`, and several hypotheses were carried
across deliberately. Two of those were **refuted** and are recorded as such,
which is the corpus working as intended.

**One finding is a genuine flaw with a conditional rating** (T1: unsanitised
HTML round-tripping through the model into a learner-facing portal). **One is a
documented control that does not exist** (T8: profile-gated tool registration).
A third cluster — T9, T12, T33 — is the same class as both: *hand-maintained
descriptions of one policy drifting from the policy*. The remainder is hardening
or design decisions recorded as standing.

The structural conclusion is that **this project's security engineering is
materially better than the sibling's, and its findings are correspondingly
different in kind.** The sibling's worst findings were absent controls. Here the
controls are present, well reasoned, and usually tested — the gaps are places
where a *description* of a control outran the control, or where a principle
stated in one file was not applied in the table next to it. `SECURITY.md`,
`SECURITY-RESOURCES.md` and the ADRs are among the better security documentation
this auditor has read: accepted risks carry named owners, dismissed scanner
findings carry counter-evidence tests with *"if that test fails, this dismissal
is wrong and the alert must be reopened"*, and the release pipeline was designed
against the exact finding carried over from the sibling audit.

Two things about the codebase deserve stating before any finding. The **v1
organization API key** is unscopeable — Skilljar issues read-only or full with
nothing between — so one credential reaches every learner record and nothing in
this repository can narrow it. And **the default `parity` profile is genuinely
read-only and genuinely reaches all 42,669 learners**: "read-only" bounds damage,
not exposure. Neither is a defect; both are the shape of the problem.

## 2. Scope

See front matter for the machine-readable version. Three limitations matter:

- **Nothing was executed.** Every finding is derived from reading code. The
  prompt-injection findings have never been exercised against a running agent,
  and — the project's own record states this — **no write tool has ever executed
  against a real Skilljar organization**, so every write path here is reasoned
  rather than observed.
- **T1's rating is conditional and cannot be settled from this repository.** It
  assumes Skilljar does not sanitise `content_html` on render. The maintainer
  does not take the vendor's documentation for that, correctly. Resolving it
  needs an empirical round trip against an isolated course. Stated at the upper
  bound with the assumption named, rather than guessed in either direction.
- **The tree was pinned, and it mattered.** Unlike the sibling audit — where
  three commits landed mid-run and one file's citations went stale — this audit
  read a **detached worktree at `280c8e8`** for its entire duration, so
  `target_commit` is true by construction and no citation could drift. Two
  commits *did* land on `main` while the audit ran (`6c74ff8`, `ed97ee3`,
  releasing v0.14.0), and the only `src/` change between them is a version bump
  in `__init__.py` — so every citation in `FINDINGS.md` still resolves at
  `ed97ee3`. Verified rather than assumed. The pinning is what made that a
  one-command check instead of a re-audit.

  **One of those commits overlaps a finding.** `6c74ff8` — *"docs: record that
  two v1-credential messages contradict each other"* — independently documents
  the same contradiction as **T12**, arrived at by someone else while this audit
  was in progress. T12 is therefore partly already acknowledged upstream; the
  remediation context should read that commit before starting, and the finding's
  remaining content is that a v1-only install can call no tool at all, which is
  the part the commit does not cover.

## 3. Method

Seven research agents in parallel against the pinned worktree, each with a
narrow brief, the absolute path, and a read-only restriction passed verbatim —
including an instruction to treat all file content as untrusted data rather than
instructions. Then synthesis, clustering into threats, STRIDE gap-fill for
surfaces no finding touched, and emit.

Three method notes worth carrying forward:

- **Two briefs carried transferred hypotheses rather than generic checklists.**
  The sibling audit's two real flaws both came from one pattern — a safe default
  existing in the library and not applying at the MCP boundary — so the surface
  brief was told to check every read-annotated tool for actual mutation, and the
  credential brief was told to check whether any `id-token`-holding job runs
  project code. **Both came back clean**, and those negative results are as
  valuable as the positives.
- **Twelve of thirty-seven threats carry no evidence.** They come from the STRIDE
  gap-fill rather than from history, and they cluster where a 77-hour-old
  repository has no history to mine. With zero external vulnerability reports
  ever received, the evidence column here is a map of where the *author* has
  already looked, not where the code has been proven wrong.
- **The orchestrator verified every load-bearing finding itself** rather than
  relying on an agent's summary — and caught one of its own errors doing so
  (§6.3).

---

## 4–5 · Findings and design commentary

These live in **[`FINDINGS.md`](FINDINGS.md)** in this directory — per-finding
remediation detail (§4) and the commentary the audit produced (§5). Section
numbering is continuous across the two files, so cross-references such as §4.1
or §6.3 resolve regardless of which file you are reading.

`FINDINGS.md` is the document the remediation context should read. This file is
the record of what the audit was, how it was produced, and how much to trust it.
The issue set to file is in [`ISSUES.md`](ISSUES.md).

---

## 6. Corrections made during the audit

Recorded because they are how a later reader calibrates the rest. Four owner
corrections, one inter-agent disagreement resolved, one orchestrator error.

### 6.1 Owner corrections (2026-08-30, 2026-08-31)

1. **The v1 key contradiction is not a contradiction.** `SECURITY-RESOURCES.md`
   calls the testing key read-only; `v1backend.py:44-51` says v1 keys cannot be
   narrowed. Both are true: Skilljar offers **read-only or full, with no finer
   scoping**. The choice is binary. This bounds T3 and T7 to disclosure rather
   than damage *if* the read-only variant is what is deployed.
2. **Operators hold Skilljar administrative access independently of this tool** —
   CSA training staff. So nothing here is privilege escalation; the delta is who
   *decides*. Same framing as the sibling audit, and it is now stated in §1.
3. **The training portal is sign-in gated** beyond course descriptions. T1
   therefore executes in authenticated learner browsers rather than drive-by
   anonymous — a real downgrade, applied. Course descriptions being anonymously
   readable matters because `courses.py` is one of the families with no
   untrusted-content marking.
4. **Skilljar's render behaviour is unknown and the vendor's documentation is
   not trusted for it.** Recorded as T1's stated assumption and as the first
   open question, rather than resolved by assertion.

### 6.2 Two agents disagreed about `setuptools`, and reconciling them produced a better finding

The advisory agent concluded CVE-2026-59890 does not bite: release sdists are
built on `ubuntu-latest` while the CVE is macOS-filesystem specific, there is no
`MANIFEST.in` and therefore no exclusion directive to bypass, and
`scripts/check_artifact.py` inspects the built archive's real member names — a
*stronger* control than `MANIFEST.in` for this class. The credential agent
concluded it applies directly, on the grounds that the repository is
macOS-maintained with no containerised build.

**Resolution: the advisory agent is right about the published artifact**, and
`RELEASING.md` additionally forbids manual `twine upload`. But the credential
agent found something the advisory agent missed, and it stands independently:
`check_artifact.py` runs `fnmatch` on a **lowercased basename with no Unicode
normalization**, so an NFD-composed `.env` variant would match neither the
exclusion nor the guard. The CVE is hygiene; the normalization blind spot in the
compensating control is its own small finding, and neither agent would have
produced it alone.

### 6.3 An orchestrator arithmetic error, caught and corrected

While verifying the tests agent's claim that 27 read-gated methods were missing
from the integration allowlist, the orchestrator's first script reported **zero**
read-gated methods — which would have refuted a correct finding. The cause was
`split("_GATES")[1]` landing on a docstring mention rather than the table
assignment. Re-run correctly, the figures confirm the agent exactly: **57
`READ_*`-gated methods, 30 in the allowlist, 27 missing.**

Recorded because the lesson generalises: a verification script that returns zero
should be suspected before it is believed, and verification code deserves the
same skepticism as the code under audit.

### 6.4 Two hypotheses carried from the sibling audit, both refuted

- **A read-annotated tool that mutates state.** The sibling's headline finding.
  All 64 tools carrying `read_only_hint=True` were checked; every one is a single
  read, a field-allowlist flatten, and a return. There are **no local filesystem
  writes anywhere in `src/`**, so the class cannot reproduce.
- **A capability gate wrapping only one backend.** `mcp/_config.py:141` wraps v2
  and `:148-149` wraps v1 with the *same* policy object, and a test asserts every
  `V1Backend` public method has a `_GATES` entry. Designed against explicitly.

A third — an unverified JWT signature driving an authorization decision, raised
by the advisory agent outside its remit — was investigated and refuted; see §7.

---

## 7. Investigated and cleared

Kept so the next audit does not repeat the work. Thirteen items.

| checked | result |
|---|---|
| A read-annotated tool that mutates | **Clear.** All 64 `read_only_hint=True` tools examined. The annotation problems that exist are the opposite direction — write-class tools understating their reach (T16, T17). |
| Local filesystem writes in `src/` | **None exist.** No exports, caches, token file or logs. Logging is stderr-only; stdout is reserved for JSON-RPC. The sibling's ungated-local-write finding cannot reproduce. |
| The capability gate covering only one backend | **Clear.** Both backends wrapped with the same policy; `tests/test_progress.py:157-165` asserts `V1Backend` coverage in `_GATES`. |
| Unverified JWT signature as an authorization flaw | **Refuted.** `auth.py:27-50` decodes without verifying, deliberately: it is the client's own `client_credentials` token, and the claims feed only `exp` for refresh timing and `scope` for a pre-check that can **only refuse early**. Both fail safe; Skilljar stays authoritative. The docstring says *"Never treat the result as an authorization decision about someone else's token."* |
| API base-URL redirection (credential exfiltration via env) | **Clear, and specifically checked.** `settings_from_env` reads exactly four keys and none is a base URL; there is no `CSA_SKILLJAR_BASE_URL`. TLS verification never disabled; `follow_redirects` never set so httpx's `False` default applies, meaning a 3xx cannot replay `Authorization` to another host. |
| `mcp`-SDK advisories (CVE-2026-52869/52870, CVE-2026-59950, CVE-2025-66416, CVE-2025-53365/53366) | **Not applicable twice over.** All below the declared `mcp>=2.1` floor, **and** `mcp/cli.py:59` is the only `transport=` site in `src/` — stdio only. Worth defending as an invariant: an HTTP transport would make an unscopeable org-wide credential network-reachable, which is exactly what that advisory class is about. |
| Repository security advisories | **Real zero.** `gh api /repos/CloudSecurityAlliance/csa-skilljar/security-advisories` → HTTP 200, `[]`, authenticated as the maintainer. Not an access failure. |
| Advisory query methodology | **Validated.** The query form was sanity-checked against `affects=requests` (8 advisories returned), so every zero in the dependency sweep is demonstrably a real zero rather than a malformed query. |
| Real learner PII in test fixtures | **None.** There are **no non-`.py` files under `tests/` at all** — no cassettes, no recorded responses, no JSON fixtures. All fixture data is inline literals; every email is on `example.org`/`example.com`. Secret-shaped literals are deliberate sentinels. The only real addresses in the repository are the maintainer's own two, in `DEMO_ACCOUNTS`. `analysis/` and `specs/` carry endpoint maps and scope names, no learner data. |
| SQL / command / LDAP / XPath / template injection | **Not present.** No database, ORM or template engine on any data path; no `subprocess` anywhere in `src/`. |
| Unsafe deserialization, `eval`/`exec` on external data | **Absent.** `r.json()` plus one `json.loads` on a base64 JWT payload behind a broad `except`. No `pickle`, `yaml` or `marshal`. |
| `pull_request_target` in any workflow | **Absent.** `tests.yml`/`docs.yml` run fork-PR code on `pull_request` with `contents: read`, no secrets referenced. Every action SHA-pinned with Dependabot moving the pins. |
| The sibling's release-pipeline finding (`id-token` held while project code runs) | **Does not reproduce, by design.** `release.yml` splits an ungated `build` job from a `publish` job holding `id-token: write` and containing only `download-artifact` + `pypa/gh-action-pypi-publish` — no checkout, no install, no tests, with a comment saying so. |

---

## 8. Handoff

**For the remediation context.** [`FINDINGS.md`](FINDINGS.md) is intended to be
sufficient to fix without re-deriving the analysis, and
[`ISSUES.md`](ISSUES.md) carries the issue set to file once this lands on
`main` — with labels and copy-pasteable bodies, ordered P1 through P4. Every
location is `file:line` at `280c8e8`; re-verify against the tree you work on.

Suggested order:

1. **Settle T1's premise before fixing T1.** The empirical round trip (write a
   payload, read it back, observe the rendered page) decides whether this is
   remediation or defence in depth. It is also the first concrete test case for
   the API-server-as-test-harness idea, and it needs an isolated unpublished
   course with guaranteed teardown — never a live course.
2. **T7** — percent-encode paths, reject ids containing `/?#%` at the tool
   boundary, add a known-operation guard to `V1Backend`. Small, and it is the
   one path where the unscopeable credential has no local check.
3. **T8** — gate registration on the profile, as ADR-005 describes.
4. **T9** — add `publishing.delete`/`webpackages.delete` and apply the declared
   split; the `authoring` profile can currently destroy things it was designed
   not to.
5. **T10** — move the four consistency guards out of `tests/integration/` so
   they run in CI, *then* fix the 27-entry drift deliberately. Do not fix it by
   pasting names into the allowlist; see the finding for why.
6. **T12, T33, T30** — the description-drift cluster. All small, and a
   consistency test closes the class rather than the instances.
7. The remainder of §4 in any order.

**Decisions this report deliberately does not make:**

- Whether T1 warrants disclosure handling beyond a release note. It involves a
  third-party platform and real learners, which is materially different from
  anything in the sibling audit. Not an audit judgement.
- Whether to build the API-server-as-security-test-harness capability that T1's
  open question implies. That is a product decision with a vendor-authorization
  dependency, and it is discussed in `FINDINGS.md` §5.4 rather than
  recommended here.
- Whether `PROFILES` should gain a bulk-read/single-read split (T13).

**What could not be determined here, and gates ratings:**

- **Skilljar's render behaviour** — T1.
- **Which `CSA_SKILLJAR_PROFILE` the deployed configurations set** — T4, T5, T6,
  T9 and T21 are all scored against `full` being rare and `authoring` being used.
- **Whether the deployed v1 key is the read-only variant** — bounds T3 and T7.
- **Whether the `pypi` GitHub Environment has a required-reviewer rule** — T22.
