# FRICTION-001: Enumerating a vendor MCP server needs a human in the loop

**Status:** Open
**Date identified:** 2026-08-26
**Type:** Process overhead

## Description

Establishing what the official Skilljar MCP server actually exposes — the ground truth the entire
parity design depends on — required a human to run an interactive OAuth browser login and then
type `/mcp`. The AI could get as far as confirming the server exists, is OAuth-gated, and which
grants it supports, all from unauthenticated discovery documents. It could not get the tool list.

The design session stalled there and could not proceed without the handoff.

## Attention tax

Noticeable. A single short interruption, but it landed at the exact point where the design needed
facts, and everything downstream was blocked on it. The prior conversation had been reasoning from
vendor prose for the same reason — and had reached a wrong conclusion (that question banks were
v1-only) because it never got this data.

## Why it is friction rather than a bug

Nothing is broken. Authorization-code + PKCE is the correct design for a remote multi-tenant
server, and requiring a human at consent is the point. The friction is that "tell me what this
server can do" is a *read* operation with no side effects, and it is gated behind the same
interactive flow as making changes.

## Possible resolutions

- A vendor-published tool manifest, or `tools/list` reachable with a machine credential. Would
  need Skilljar to offer it; worth raising as feedback.
- Once `WAITING-FOR-002` lands, test whether an `api.skilljar.com` client-credentials token is
  accepted by `mcp.skilljar.com`. Its metadata says no, but the check is cheap and settles it.
- Failing both: snapshot the registry once, check it into `specs/`, and diff on a cadence — which
  is what `check_upstream.py` will do anyway (ADR-006). That converts a recurring interruption
  into a single one.

## Notes

Generalises past this vendor. Any MCP server behind interactive OAuth has the same property, and
any project doing compatibility work against one will hit it. Worth mentioning to
CINO-Platform-Engineering if a second instance appears.
