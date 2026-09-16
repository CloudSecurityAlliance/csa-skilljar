# Upstream API spec snapshots

Fetched **2026-08-26** from `api.skilljar.com`, unauthenticated. These are snapshots of
someone else's moving target; re-fetch and diff before trusting them. Skilljar publishes
no version stamp or `revision` field on either document — `info.version` is a constant
(`1.0.0` / `2.0.0`) and does not move when the surface changes — so **the sha256 below is
the only identity these files have**. That is why this file exists.

Skilljar publishes the v1 document as OpenAPI 3.0.3 YAML and the v2 document as OpenAPI
3.1.0 JSON. Both are served from the same host the API itself runs on, and both are
linked from the vendor's own documentation pages (kept in `docs-html/`), so they are
authoritative rather than best-effort reconstructions.

## What is here

| file | what | source URL | sha256 | bytes |
|---|---|---|---|---|
| `skilljar-v1-openapi.yml` | v1, OpenAPI 3.0.3 — 160 paths / 340 ops / 420 schemas. **The as-fetched artifact.** | https://api.skilljar.com/docs/schema.yml | `3d3becd2f8b08aba…` | 733116 |
| `skilljar-v1-openapi.json` | v1, **derived** — a lossless YAML→JSON conversion of the file above, not a separate fetch. Exists so tooling needs no YAML parser (`scripts/check_docs.py`). | *(derived, no URL)* | `9b81492883377fb0…` | 971059 |
| `skilljar-v2-openapi.json` | v2, OpenAPI 3.1.0 — 44 paths / 82 ops / 263 schemas, as fetched | https://api.skilljar.com/v2/openapi.json | `f8025de20169a06e…` | 359552 |

Full digests:

```
3d3becd2f8b08abac0fdc26c20ec597a43d21a3e6e8b81fbbeb3bb3d5cfe0a0b  skilljar-v1-openapi.yml
9b81492883377fb0a655a7ca4ae3316eb7596f617aa0beded9ecfdd573ff8769  skilljar-v1-openapi.json
f8025de20169a06ed1338f54d531b746e9794fc4ff60d27babd961525e8bf006  skilljar-v2-openapi.json
```

Re-verify with:

```
shasum -a 256 specs/skilljar-v1-openapi.yml specs/skilljar-v1-openapi.json specs/skilljar-v2-openapi.json
```

## Drift as of 2026-09-16

Both source URLs were re-fetched on 2026-09-16 and compared against the stored copies.

**v1 has not drifted.** The live `docs/schema.yml` is **byte-identical** to
`skilljar-v1-openapi.yml` — same sha256, same 733116 bytes. Twenty-one days, no change.
`skilljar-v1-openapi.json` was re-confirmed as a faithful conversion of it (both parse to
the same object).

**v2 has drifted**, in three separate ways. Live document on 2026-09-16:

```
9fc34e55336d21951330dacade59aacc050f01937bc215fd1e1963a44f9ca6ac  (live, 407465 bytes)
```

1. **Four new paths** (44 → 48), eight new operations (82 → 90). Nothing was removed.
   - `/v2/assets/`, `/v2/assets/{id}` — the ADR-002 retirement trigger firing, already
     tracked in `TODO.md`; `scripts/check_upstream.py` reports these.
   - `/v2/students/{id}/relationships/domain-memberships/`,
     `/v2/students/{id}/relationships/domain-memberships/{domain_id}` — **not** previously
     recorded anywhere in this repo.

2. **The response media type changed globally**, on every one of the 79 pre-existing
   operations that declare a response body: `application/json` →
   `application/vnd.api+json`. Request bodies are unaffected — all 43 still declare
   `application/json`. Confirmed against the live API, not just the document: an
   unauthenticated `GET /v2/courses/` sent with `Accept: application/json` still answers,
   and answers with `content-type: application/vnd.api+json`. So this is a declaration
   catching up with JSON:API, not a content negotiation the client has to satisfy.

3. **Twenty-six new schemas** (263 → 289), none removed, and eight changed. The new ones
   are the `Asset*` and `DomainMembership*` families backing the new paths, plus
   `FlashcardCard` / `FlashcardConfig`. The eight changed schemas are additive:
   - `ContentItemRequest` / `ContentItemResource` — new `FLASHCARD` content-item type and
     a `flashcard` config property.
   - `LessonAttributes` / `LessonDetailAttributes` / `LessonCreateRequest` /
     `LessonUpdateRequest` — a new `WEB_PACKAGE` lesson type with `web_package_id`,
     `width_px`, `height_px` (the last two three-valued on PATCH).
   - `DomainIdentifier` / `DomainRelationship` — description only, no shape change.

The v2 snapshot is **deliberately not refreshed here**. Refreshing it is what silences
`scripts/check_upstream.py`, and per that script's own instruction it has to happen
together with `analysis/`, the regenerated scopes, and the coverage map — one change, not
a spec bump on its own.

### What `check_upstream.py` does and does not see

`scripts/check_upstream.py` compares the live v2 **path set** against
`skilljar-v2-openapi.json`, the advertised scope catalogue against
`analysis/live-authz-metadata.json`, probes 31 reserved scope areas for 401-vs-404, and
probes the `client_credentials` grant. It does **not** look at v1 at all, does not compare
operations, schemas, media types or parameters, and does not verify that the files in
`specs/` are the bytes that were fetched. Findings 2 and 3 above are invisible to it —
they were found by diffing the documents, not the path lists.

## Captured MCP tool registry

`official-mcp/` is a different kind of artifact: captured 2026-08-26 from an authenticated
session against `https://mcp.skilljar.com/mcp`, and **not re-fetchable** without an
interactive OAuth browser login (FRICTION-001). There is no upstream URL to diff it
against, so its digests are the only integrity record it will ever have. See
`official-mcp/README.md` for what it contains and why.

```
4db4551d767dc10877e376902fcd9459f0f8cf4100469bb5e7453e9741427f70  official-mcp/tool-names.json
643261ab41d5af4324759ede81d57fe9c635260d11a02c80d29c3923bd985f71  official-mcp/registry-list-tools.json
f5a2f58e8dadb2ffb1513d5f427da6edda89744252ce28033cbbe0f242c45ea6  official-mcp/registry-get-delete-tools.json
0ed6f7a8b0fcdb0b0a69c715776ec144c53dc9c2cd3bcbd6ee863ce83df05e19  official-mcp/registry-create-tools.json
e961c93a04c92a32d92a998cb689bf9f2cb72ae53b9a3880ebdf5bc02f46d6a6  official-mcp/registry-update-tools.json
b4f9d2d6b83fbcd30371f91f8b173d5280ae8ad51907d124fcce0d2e5a6be289  official-mcp/registry-people-tools.json
8c47cc42d1ebac44b960c4f363cdbc40d069218167d199ad2b5ce688d4c5c73e  official-mcp/registry-binding-publishing-tools.json
```
