# Block 12 — Assets & media — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** The asset library — the files a course is actually made of — which v2 cannot see
at all.

**Spec:** v1 OpenAPI `specs/skilljar-v1-openapi.json` · ADR-002 (routing) · ADR-007 (order)

## Global Constraints

Unchanged. Writes remain off against Skilljar (`WAITING-FOR-003`); reads are exercised
live.

---

## Routing — the ADR-002 split is not the obvious one

v1 has five asset-and-media paths and **only some are ours**:

| v1 path | v2 equivalent | Ours? |
|---|---|---|
| `/v1/assets` | **none** | **yes** — v2 has no assets endpoint at all |
| `/v1/assets/{id}` | **none** | **yes** |
| `/v1/web-packages` | `/v2/web-packages/` | no — v2 owns it (Block 9) |
| `/v1/web-packages/{id}` | `/v2/web-packages/{id}` | no — v2 owns it |
| `/v1/web-packages/{id}/lessons` | **none** | **yes** — attaching a package to lessons |

So this block adds assets, and exactly one web-package capability. Adding v1 web-package
listing "for completeness" would put the same capability on two backends with two data
shapes, which is what ADR-002 forbids.

## What probing established

Read-only, against the live API, 2026-08-28.

**157 assets, all on one page.** `count: 157`, `next: null`. The endpoint is DRF-enveloped
but does not actually paginate at this size.

**Types:** `PDF` 79, `VIDEO_BOTR` 34, `FILE` 23, `TEMPLATE` 21.

**`aspect_ratio` is `16:9` for all 157 — including every PDF.** It is a default, not a
measurement, and reporting a PDF's aspect ratio as meaningful would be wrong.

**The detail view carries a field the listing does not: `download_url`.** That is the
entire reason `get_asset` exists alongside `list_assets`.

### `download_url` is a presigned, expiring, credential-free download link

| Property | Value |
|---|---|
| Host | `everpath-course-content.s3.amazonaws.com` |
| Query | `AWSAccessKeyId`, `Expires`, `Signature` |
| Lifetime | **60 minutes** |
| Stable between fetches? | **No** — a new URL each time |
| Works without Skilljar credentials? | **Yes** — verified with a ranged GET: `206`, `application/pdf`, `bytes 0-0/7455694` |

That last row is the important one. **The URL is a bearer capability.** Anyone who sees it
can download the file for an hour with no authentication whatsoever — so a `download_url`
pasted into a transcript, a ticket or a screenshot is a working link to course content for
whoever reads it. This connects directly to the transcript-persistence concern already in
`DATA-RESOURCES.md`.

## The traps

| # | Trap | Fails how | Pinned by |
|---|---|---|---|
| 1 | `download_url` is a **credential-free, 60-minute** download link | Quietly, and outside the system — a link in a transcript keeps working | `test_download_url_is_described_as_a_bearer_capability` |
| 2 | It **changes on every fetch** | A cached or stored URL expires and looks like a broken asset | `test_the_url_is_documented_as_unstable_and_uncacheable` |
| 3 | Only the **detail** view has it | A caller lists assets, finds no URL, and concludes there is none | `test_list_does_not_carry_a_download_url` |
| 4 | `aspect_ratio` is `16:9` for **every** asset, PDFs included | Reported as fact about a document | `test_aspect_ratio_is_not_presented_as_meaningful_for_documents` |
| 5 | v1 web-package listing must **not** be added — v2 owns it | Two shapes for one capability (ADR-002) | `test_no_capability_is_served_by_both_backends` (existing) |

## Files

- Modify: `src/csa_skilljar/v1backend.py` — `list_assets`, `get_asset`, and the fake
- Create: `src/csa_skilljar/mcp/_tools/assets.py`, `tests/test_assets.py`
- Modify: `client.py`, `_schemas.py`, `policy.py` (`content.read` — an asset is content),
  `server.py`, `_tools/__init__.py`
- Modify: the coverage tables; `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`
- Modify: `DATA-RESOURCES.md` and `SECURITY-RESOURCES.md` — a credential-free download
  link is a new egress path and belongs in both

## Capability

`content.read`. An asset is course content, and `list_lessons` already returns
`content_asset_id` under the same gate — putting assets behind a stricter one would leave
a caller able to see the reference but not resolve it.

## Task sequence

- [ ] **Task 1 — backend.** `list_assets`, `get_asset`, fake with both shapes.
- [ ] **Task 2 — tools**, with the presigned-URL warnings.
- [ ] **Task 3 — the security docs**, because this is a new egress path.
- [ ] **Task 4 — mutations, live read check, docs, PR.**

**Ships:** v0.11.0.
