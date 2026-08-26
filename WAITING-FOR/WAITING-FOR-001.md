# WAITING-FOR-001: Skilljar v2 endpoints for the reserved scopes

**Status:** Open
**Date identified:** 2026-08-26
**Type:** Technology

## Waiting for

Skilljar to ship the v2 API endpoints for capabilities they have already reserved OAuth scopes
for — webhooks, paths, assets, tags, labels, content-items, instructors, course-families,
catalog-pages, plans, themes, and the commerce stack.

## Why waiting

We are **not** waiting to start — those capabilities are being built now over v1 (ADR-002,
ADR-007). What we are waiting for is the trigger to *retire* each v1 family and re-point its tools
at v2.

The evidence that this is coming is unusually good. `api.skilljar.com`'s authorization-server
metadata advertises **88 scopes**; the published v2 OpenAPI document uses **28**. Probing all 31
undocumented scope areas returns `404`, against a control that correctly separates `401` (exists,
needs auth) from `404` (not built). So the scopes are a published roadmap and the endpoints are
not built yet.

Building against v1 in the meantime is the right call: v1 works today, the capabilities are needed
today, and because no tool name carries a version (ADR-004), the eventual switch is invisible to
callers.

## Trigger

**Per-area and mechanically checkable:** `GET https://api.skilljar.com/v2/<area>/` returns
anything other than `404`. A `401` means the endpoint exists and needs authentication — that is
the signal.

`scripts/check_upstream.py` performs this check weekly and opens an issue when any area flips.

Priority order for retirement, matching the phase order: `webhooks` · `assets` · `paths` ·
commerce (`offers`, `promo-codes`, `orders`, `training-credits`, `licensing`, `access-codes`) ·
`vilt-sessions` · `labels` · `tags`.

## Next action

None required. `check_upstream.py` is the watcher; this entry documents what its output means.

## Notes

Per-lesson learner progress has **no reserved scope** in the catalogue — there is no
`lesson-progress:*`. That capability may be intended to arrive under `enrollments:*`, or may not
be planned for v2 at all. Worth re-checking when the first areas flip, because it is the family
this project ranks first.
