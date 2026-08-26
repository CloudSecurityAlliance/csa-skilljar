# WAITING-FOR-002: A v2 OAuth client for development

**Status:** Open
**Date identified:** 2026-08-26
**Type:** Person/Response

## Waiting for

A Skilljar v2 API client — client id and secret — issued for this project's development and
testing.

## Why waiting

Phase 1 is entirely v2. We currently have two credentials, and neither is usable for building it:

- `CINO_READ_ONLY_TESTING_KEY` — a **v1** organisation API key. Verified working across every v1
  family, but v1 only.
- The official Skilljar MCP server, authorised interactively in a Claude Code session. That grants
  access to *their* server, not a credential we can drive our own client with. Its authorization
  server does not offer `client_credentials` at all (ADR-003).

So every v2 fact in the design was established from the published OpenAPI document and from calls
made through Skilljar's own MCP server. That was enough to design against; it is not enough to
build and test against.

Credential issuance is explicitly not delegated to AI (see `RACI.md`).

## Trigger

`CSA_SKILLJAR_V2_CLIENT_ID` and `CSA_SKILLJAR_V2_CLIENT_SECRET` available to the project, and
`POST https://api.skilljar.com/v2/auth/token` returning an access token for them.

## Next action

Kurt issues a v2 API client in the Skilljar Dashboard.

**Scope it narrowly.** For Phase 1 development the read scopes plus the content-authoring write
scopes are sufficient:

```
courses:read courses:write  lessons:read lessons:write
quizzes:read quizzes:write  question-banks:read question-banks:write
domains:read published-courses:read enrollments:read students:read
analytics:read certificates:read web-packages:read signup-fields:read
student-groups:read
```

Deliberately excluded until there is a reason: `students:write`, `students:anonymize`,
`students:deactivate`, `students:manage-password`, `clients:write`, and the remaining write
scopes. Testing destructive paths against production is not something to enable by default.

## Notes

A second, deliberately narrower client would let us test the local scope pre-check (design spec
§5.4) — the error that names exactly which scope is missing. Useful, not blocking.
