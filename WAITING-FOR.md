# Waiting For

Conditions that need to be true before it makes sense to proceed. Each entry has a **specific,
observable trigger** — without one it is a wish, not a WAITING-FOR.

| ID | Title | Status | Type | Date |
|----|-------|--------|------|------|
| WAITING-FOR-001 | Skilljar v2 endpoints for the reserved scopes | Open | Technology | 2026-08-26 |
| WAITING-FOR-002 | A v2 OAuth client for development | **CLOSED 2026-08-27** | Person/Response | 2026-08-26 |
| WAITING-FOR-003 | A safe place to test writes against Skilljar | Open | Person/Response | 2026-08-27 |

**WAITING-FOR-003 is the one that constrains current work.** Writes to Skilljar are OFF and
enforced, not merely conventional — see that entry for the three layers. Nothing in
`tests/integration/` may mutate a real organization until Hannah confirms where writes may go.
