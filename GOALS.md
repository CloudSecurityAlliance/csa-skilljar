# Goals

## North Star

CSA's training operations — course authoring, exam item banks, enrolment, and progress
reporting — can be driven end to end by scripts and AI agents, against whichever Skilljar API
actually has the capability, **without the caller ever needing to know which one**. When Skilljar
finishes building v2, this project quietly gets smaller and nothing that depends on it changes.

## Near-term (now → Phase 2)

| Goal | Success metric |
|---|---|
| Ship Phase 1 parity | All 73 official tool names implemented over v2, with identical argument names; a registry-diff test passes against the live official server |
| Be installable | `pip install csa-skilljar` from PyPI, published via Trusted Publishing with attestations |
| Be testable offline | The entire tool surface exercisable with no network and no credentials, via `FakeBackend`; coverage floor enforced in CI |
| Detect upstream drift automatically | `scripts/check_upstream.py` runs weekly in CI and opens an issue when Skilljar's v2 surface, scope catalogue, or official tool registry changes |
| Never fail obscurely on credentials | Each of the seven auth states in the design spec produces a distinct, actionable message; verified by test |

## Medium-term (Phases 3–9)

Add the v1-only families, ordered by evidence of use in CSA's own org rather than by API size:
learner progress → assets and media → commerce (read-biased) → learning paths → events and
webhooks → instructor-led training → labels and tags.

| Goal | Success metric |
|---|---|
| Close the reporting gap | Per-lesson learner progress reachable from an MCP client — v2 reports course-level completion only |
| Make content assets scriptable | Asset upload works; v2 has no file upload at all |
| One demonstration that is also the end-to-end test | A single plan exercises 100% of registered tools, computed from the registry, run against both the fake and real Skilljar |

## Long-term

| Goal | Success metric |
|---|---|
| **Shrink** | Each v1 family retired as the v2 equivalent ships, with no tool renamed and no caller changed. A shrinking `V1Backend` is the project succeeding, not failing. |
| Feed the pattern library | This is CSA's third MCP server and the first with two upstream APIs. The five research questions in the design spec §10 get answered and folded into CINO-Platform-Engineering. |
| Be useful outside CSA | Adopted by at least one Skilljar customer who is not CSA |

## Who benefits

- **CSA** — training content pipeline becomes scriptable; exam item banks become programmatically
  manageable; reporting stops being a manual export.
- **The community** — any Skilljar customer gets the same capability, free and open source. The
  README points people at Skilljar's own server first, so the value here is specifically the gap.
- **Shared** — a worked public example of an MCP server over two API generations with divergent
  auth and data models, which is a shape more integrations will hit as vendors version their APIs.

## Non-goals

Named so they are decisions rather than drift: no webhook *receiving*, no caching layer, no
cross-API composite writes, no catalog page-building, and no v1 families with no data in the
reference org. Rationale in the design spec §2.

## How we would know this failed

- Tool descriptions are accurate but unusable cold — the demonstration is the test for this, and
  it is the failure mode most likely to go unnoticed.
- The two-API seam leaks: callers start needing to know whether a capability is v1 or v2.
- Upstream drift is discovered by a user rather than by CI.
