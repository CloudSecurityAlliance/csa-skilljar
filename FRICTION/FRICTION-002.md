# FRICTION-002: Vendor documentation contradicts the vendor's own API

**Status:** Accepted
**Date identified:** 2026-08-26
**Type:** Process overhead

## Description

Skilljar's published material disagreed with Skilljar's published API in several places, each of
which cost time to detect and would have produced a wrong design if believed:

- A widely-repeated claim that **question banks are v1-only**. v2 has full CRUD plus quiz-to-bank
  binding — and v1 is the weaker of the two, unable to add a question to a bank at all.
- Release notes stating the MCP server **does not work with Claude**, alongside a support article
  documenting exactly that.
- Two composite endpoints (`build_course`, `create_quiz_and_questions`) described as existing.
  They appear in neither the v2 spec nor the server's tool registry.
- The v2 docs URL **404s with a trailing slash** and serves with none.
- The authorization server advertises **88 OAuth scopes** for an API that implements 28.

## Attention tax

Significant during design. Every vendor claim had to be independently verified before it could be
built on, which roughly doubled the research phase.

## Why Accepted rather than Open

Not ours to fix, and not worth waiting on. The mitigation is already policy: **probe beats docs**,
recorded in `CLAUDE.md` and applied throughout the design spec — every factual claim in it was
confirmed against a live endpoint or a published OpenAPI document, and Appendix C lists the
evidence per claim.

## Outcome

The cost is now bounded rather than recurring: `scripts/check_upstream.py` re-verifies the facts
that matter on a schedule, so the next contradiction is caught by CI rather than by someone
building on it. Documenting the discrepancies publicly in this repo also saves the next person the
same day.
