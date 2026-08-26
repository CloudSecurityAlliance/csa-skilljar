# Business Case

## Executive summary

CSA runs its training on Skilljar. Skilljar's own MCP server covers only their v2 API, which
leaves learner progress reporting, webhooks, asset upload, learning paths and the commerce stack
unreachable from any AI client. This project closes that gap so CSA's training operations can be
driven by scripts and agents, and it is deliberately designed to shrink as Skilljar finishes
building v2.

**Benefit categories:** Synergy (primary) · Research / Exploration (primary) · Brand (secondary)

## CSA value

- **Synergy — the main argument.** CSA's training content pipeline, exam item-bank work, and
  course reporting all currently need a human in the loop for anything the v2 API does not reach.
  Per-lesson progress and asset upload are the two that bite most often. This makes the whole
  platform addressable from the tooling CSA already builds on.
- **Item-bank management specifically.** Question banks turned out to have full CRUD in v2, which
  reverses a published claim we found during research. That capability underpins reusable exam
  content across certifications, and it is now reachable programmatically.
- **Internal capability.** This is CSA's third MCP server and the first over two API generations
  with different auth mechanisms and incompatible data models. The patterns transfer.

## Community value

Free and open source under Apache-2.0, useful to any Skilljar customer. The README recommends
Skilljar's own server first and without reservation — the value offered here is specifically the
v1 gap, honestly scoped.

The public artefact also documents things Skilljar's own documentation gets wrong. Our probes
found the v2 docs URL 404s with a trailing slash, that question banks are in both APIs despite a
published claim otherwise, and that the advertised OAuth scope catalogue runs three times ahead of
the shipped API. Writing that down publicly saves the next person the same day of work.

## Shared value

A worked public example of an MCP server spanning two API generations. As vendors increasingly
ship a v2 alongside a long-lived v1, "which backend serves this tool, and how do you keep the
caller from caring" becomes a recurring integration problem. This is one answer, in the open.

## AI Enablement

**Who becomes more AI-capable:** CSA's training and certification staff, and any Skilljar
customer's education team. The capability shift is from "an agent can author course content" to
"an agent can author content, manage exam item banks, upload media, and report on learner
progress" — the operational half of running a training programme, not just the writing half.

**Mechanism:** both. *Friction removal* for work that already happens through the v2 API but
breaks down at the seams (a course-building agent that cannot upload the image it just referenced).
*Novel-surface creation* for the v1-only capabilities, which no AI client can reach today by any
route.

**Counterfactual:** the gap stays until Skilljar closes it. They have publicly reserved OAuth
scopes for webhooks, paths, assets, tags and commerce, so they clearly intend to — but those
endpoints return 404 today and there is no published date. No one else is building this: Skilljar
is a mid-sized commercial platform with no third-party MCP ecosystem. Realistically, if CSA does
not build it, CSA waits.

**This is a diminishing-value project by design, and that is stated on purpose.** The honest
version of the case is that we are buying capability during a window, not building a permanent
asset.

## Resources

- **Staff:** one engineer working through AI, part-time. No headcount request.
- **Budget:** zero marginal cost. Public GitHub, PyPI, GitHub Actions on free tiers.
- **Timeline:** Phase 1 (parity) is the near-term deliverable. Later phases are demand-driven —
  each v1 family is independently shippable, so the project can stop at any phase boundary
  without leaving anything half-built.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Skilljar ships v2 coverage and this becomes redundant | Medium | **This is the plan, not a risk to avoid.** Tool names never carry a version, so retiring a v1 backend changes nothing for callers. `check_upstream.py` tells us when to retire each family. |
| An operator configures an over-broad credential | High | v2 declares a required scope per operation; the design bakes those into tool metadata and pre-checks locally. Capability profiles gate what an install can do at all. Docs push least privilege. |
| Prompt injection via course content → destructive tool call | High | Named as the primary threat in `SECURITY-RESOURCES.md`. Destructive capabilities ship present-and-off; the policy cannot be widened in-band. |
| v1 is deprecated with short notice | Medium | v1 remains Skilljar's larger and more complete API and their docs treat it as current. If deprecation is announced, the affected families are the ones already scheduled for retirement. |
| Vendor terms of service | Low | The project is an ordinary API client using published, documented endpoints with customer-issued credentials. No scraping, no undocumented endpoints in shipped code, no credential sharing. Worth a review before any promotion beyond CSA. |
| Maintainer bus factor | Medium | Public repo, spec-first, every decision logged as an ADR. The design spec is written so someone else can pick it up. |

## Operational burden

- **Technical operations:** one scheduled CI job (`check_upstream.py`). No deployed service, no
  database, no infrastructure — it is a library and a local process on the user's machine.
- **Human operations:** issue triage on a public repo. Expected to be near zero initially.
- **Knowledge operations:** the real cost. The coverage map goes stale whenever Skilljar ships,
  which is why drift detection is a script rather than a documented ritual.
- **Total ongoing:** well under 0.05 FTE outside active development phases.
- **Minimisation strategy:** no hosted surface to operate; drift detection automated rather than
  remembered; each phase independently shippable so there is no half-finished state to carry.
- **Burden-exceeds-value trigger:** when Skilljar's v2 covers the families CSA actually uses —
  concretely, when `/v2/webhooks/` and per-lesson progress return anything other than 404 — the
  remaining v1 code should be retired and the project reassessed for whether it should exist at
  all. That is a success condition.

## Success metrics

- All 73 official tool names implemented, verified by a registry diff against the live server
- `pip install csa-skilljar` works from PyPI with build attestations
- At least one CSA training workflow that previously required manual work runs unattended
- The five research questions in design spec §10 answered and contributed to
  CINO-Platform-Engineering
- At least one v1 family retired because v2 shipped it — the clearest signal the design was right
