# Goals

Shared goals for CSA's MCP server fleet — library-first, local stdio, one fail-closed seam at the
data boundary, offline-testable, published to PyPI with attestations — are stated once in the fleet
roster (`surfaces/mcp/ROSTER.md` in the internal CINO-Platform-Engineering repo) and are not
restated here. This file records only what is specific to Skilljar.

## North Star

CSA's training operations — course authoring, exam item banks, enrolment, grading, and progress
reporting — can be driven end to end by scripts and AI agents, **against whatever route actually
has the capability**, without the caller ever needing to know which one. Three routes exist: the v2
API, the v1 API, and the dashboard, which has no API at all.

When Skilljar finishes building v2, this project quietly gets smaller and nothing that depends on it
changes.

**The third route is not a workaround.** Grading is the clearest case: a learner submits a free-form
response, Skilljar creates a task, and a human scores it in the web UI. Probing on 2026-09-02 found
no grading API in either version and none reserved. A goal of "100% API coverage" would score this
project complete while the capability CSA staff use most often remained unreachable. The unit is the
**capability**, not the API.

## Near-term

| Goal | Success metric |
|---|---|
| **Remediate the 2026-08-30 audit** | The 18 T-numbered findings tracked under [#76](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/76) are closed or explicitly accepted. This is the dominant fact about the project's current state, and four findings are the reason: unsanitised HTML round-tripping through the model into the learner-facing portal ([#55](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/55)), `authoring` able to destroy despite a declared delete/write split ([#58](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/58)), `client.credentials` reaching around the capability gate ([#67](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/67)), and `send_password_reset` emailing real people with no confirm gate ([#61](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/61)) |
| **Guards that can fail** | Every gate has a test that has been proven to fire by breaking it. Three tests that cannot fail are open now ([#72](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/72)), and the read-only integration guard is dead with no safe repair ([#59](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/59)) |
| **A safe place to test writes** | Every write path exercised against a real organization that is not CSA's production one. Blocked on [WAITING-FOR-003](WAITING-FOR/WAITING-FOR-003.md); until it clears, writes stay OFF and enforced in three layers rather than by convention |
| **Distinct, actionable credential failure** | Each of the seven auth states produces its own message, verified by test. Skilljar has no login and no browser step — the credential *is* the identity — and nothing said so where people looked ([FRICTION-004](FRICTION/FRICTION-004.md)) |
| **Docs that cannot drift from the surface** | Tool counts and capability claims are generated or asserted, not hand-written. Four different counts appear across current docs |

## Medium-term

- **Grow the dashboard backend by frequency, not completeness.** Anything CSA staff do repeatedly
  in the web UI is in scope; one-off administration — billing, org settings, theming, account
  deletion — is deliberately out. Two dashboard tools ship today; grading is the next one that earns
  its place.
- **Drift detection covering all three routes.** `check_upstream.py` already works for the APIs and
  has opened four issues unprompted ([#13](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/13),
  [#83](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/83),
  [#85](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/85)). The dashboard route has
  none, and a UI has no contract — it breaks silently on a redesign. Capability coverage via a web
  route without drift detection is choosing silent breakage.
- **Close the reporting gap** — per-lesson learner progress, which v2 reports only at course level.
- **Make content assets scriptable** — v2 has no file upload at all.

## Long-term

| Goal | Success metric |
|---|---|
| **Shrink** | Each v1 family retired as the v2 equivalent ships, with no tool renamed and no caller changed. **The trigger has fired once already** — Skilljar shipped `/v2/assets/` and ADR-002's retirement condition activated ([#81](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/81)). A shrinking `V1Backend` is the project succeeding, not failing |
| **Be useful outside CSA** | Adopted by at least one Skilljar customer who is not CSA |

## Non-goals

Named so they are decisions rather than drift. Rationale in the design spec §2.

- **No webhook receiving**, no caching layer, no cross-API composite writes, no catalog page-building.
- **No v1 families with no data in the reference org** — phase order follows usage evidence, not API
  size (ADR-007).
- **No one-off dashboard administration.** The dashboard backend exists for repeated work. Billing
  and org settings stay in the browser where they are done twice a year.
- **No version marker in any tool name** (ADR-004). Which route serves a call is this project's
  problem, not the caller's — that is the North Star restated as a constraint.

## How we would know this failed

1. **Tool descriptions are accurate but unusable cold.** The demonstration plan is the test for this,
   and it remains the failure most likely to go unnoticed.
2. **The route seam leaks** — callers start needing to know whether a capability is v2, v1 or
   dashboard. A version marker appearing in a tool name is the visible symptom.
3. **Upstream drift is discovered by a user rather than by CI.** Currently CI wins; the dashboard
   route is where this will break first, because nothing watches it.
4. **A guard is green and asserts nothing.** Already true in three places right now.
5. **The audit findings age into normality.** Eighteen open findings against one closed issue in the
   repo's entire history is the shape of a backlog that has stopped being read as urgent.

## Who benefits

- **CSA** — the training content pipeline becomes scriptable, exam item banks programmatically
  manageable, reporting no longer a manual export, and grading reachable at all.
- **The community** — any Skilljar customer gets the same capability, free and open source. The
  README points people at Skilljar's own server first; the value here is specifically the gap.
- **Shared** — a worked public example of an MCP server spanning two API generations *and* a
  no-API surface, which is a shape more integrations will hit as vendors version and under-build
  their APIs.
