# WAITING-FOR-002: A v2 OAuth client for development

**Status:** CLOSED 2026-08-27
**Date identified:** 2026-08-26
**Type:** Person/Response

## Waiting for

A Skilljar v2 API client — client id and secret — issued for this project's development and
testing.

## Why waiting

Phase 1 is entirely v2. We currently have two credentials, and neither is usable for building it:

- `CSA_SKILLJAR_V1_API_KEY` — a **v1** organisation API key. Verified working across every v1
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

---

## Resolution — 2026-08-27

Kurt issued a v2 API client and placed its id and secret in the repository's `.env`. The
trigger is met: `POST https://api.skilljar.com/v2/auth/token` returns an access token.

The client was scoped to exactly the 17 scopes recommended above — no `students:write`,
nothing destructive, no `clients:write`.

**What first contact with a real token established**, none of which could be settled by
probing without one:

| Question | Answer |
|---|---|
| Does the grant need a `scope` parameter? | **No.** Sending none returns every scope the client was issued. |
| Where are the granted scopes? | A **`scopes`** claim holding a JSON **list**. Not `scope`, and not a space-delimited string. |
| Token lifetime | `expires_in: 900` (15 minutes). The JWT's `exp` agrees. |
| Other claims | `aud`, `iss` (both `skilljar-api-v2`), `iat`, `jti`, `client_id`, `organization_id` |
| Is the client organization-bound? | **Yes** — `organization_id` is in the token. Unlike a dynamically registered client (see `register_oauth_client`, which binds none). |
| Refresh token | One is returned, which RFC 6749 §4.4.3 says SHOULD NOT happen for `client_credentials`. We ignore it; re-granting is stateless and cheap, and holding one would reintroduce the token custody ADR-003 exists to avoid. |

**It found a blocking defect immediately.** `auth.py` read the standard `scope` claim, so
`granted_scopes()` returned empty for every real token and the scope pre-check refused
*every* scoped call — with a message telling the operator to re-issue a credential that
was correctly scoped. The offline suite was green throughout, because its JWT fixture
could only produce the shape the code already expected. Fixed, with regression tests for
both shapes.

**Verified against live Skilljar:**

- `check_access` reports v2 working, 17 scopes, token expiry.
- `list_courses` returns real courses from the CSA organization.
- The scope pre-check refuses `publish_courses`, `add_group_memberships`,
  `create_web_packages` and `create_students` locally, naming the exact missing scope,
  with **zero network traffic** — proven by a backend whose HTTP layer raises if touched
  (design spec §5.4, previously untested).
- The capability gate refuses before the scope check even runs: under the default
  `parity` profile, `create_students` is stopped by `people.write` first.
- `tests/integration/` — all 15 pass.

The narrower second client suggested below is no longer needed: the issued client
already lacks several write scopes, which is what exercised the pre-check.