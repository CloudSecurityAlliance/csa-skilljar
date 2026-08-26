# FRICTION-003: The AI asked for resources it could have found itself

**Status:** Resolved
**Date identified:** 2026-08-26
**Date resolved:** 2026-08-26
**Type:** AI-inefficient

## Description

Across the design session, roughly five of fourteen exchanges were the human supplying
something the AI should have found or done unprompted:

| What the human supplied | What should have happened |
|---|---|
| "in `./.env` we have a read-only key" | Look. Phase 0 was declared blocked on a v1 API key sitting in this repo's own `.env`. |
| "extract data before I remove it" | Recognise that the connected MCP server was **perishable access** and harvest the whole registry on first contact. |
| "can you review what the official server does" | Probe the unauthenticated discovery documents first — they answered most of it for free, two minutes later. |
| "write the readme/GOALS/roadmap" | Propose the whole CINO file set once the project was registered; the convention determined it. |
| "can you download the docs" | Offer it the moment the docs were declared unreadable. |

## Attention tax

Noticeable, and asymmetric. Each was a small interruption for the human, but each one
stalled the AI completely until answered — so the cost lands as elapsed time and
context-switching rather than effort.

## The instructive one

`FRICTION-001` — *"enumerating a vendor MCP server needs a human in the loop"* — was
**written by the AI** during the same session, and the conclusion that access was
therefore perishable and should be harvested completely was not drawn. The analysis was
correct and unacted upon. Had the server been disconnected first, the 73-tool parity
baseline would have been lost permanently, and ADR-006 rests on it.

That is the failure worth remembering: not missing information, but failing to act on a
constraint already identified in writing.

## Resolution

Four operating rules added to `CLAUDE.md` — inventory before declaring a blocker,
harvest perishable access completely, probe before asking, complete a convention once
invoked — plus an explicit autonomy contract so the same class of permission is not
re-litigated each time.

## Outcome

The rules are in the file every agent session loads, phrased as what was violated rather
than as aspirations, so the next reader gets the reason and not just the instruction.
