# Official Skilljar MCP server — captured registry

**Captured 2026-08-26** from a live authenticated session against `https://mcp.skilljar.com/mcp`.
All **73 tools**, with exact argument names, defaults, enums, and the behavioural notes carried in
each tool's description.

## Why this exists

This is the **parity baseline** for [ADR-006](../../DECISIONS-ADR/ADR-006.md). Reading the live
registry requires an interactive OAuth browser login ([FRICTION-001](../../FRICTION/FRICTION-001.md)),
so it cannot be re-derived on demand or in CI. Captured before disconnecting the server.

Much of what is here is **not in the published OpenAPI document**: cascade semantics, batch dedup
rules, cross-state validation boundaries, async processing behaviour, and a number of quirks that
would otherwise have to be discovered by breaking production.

## Files

| File | Tools |
|---|---|
| `tool-names.json` | all 73 names |
| `registry-list-tools.json` | 16 list tools |
| `registry-get-delete-tools.json` | 14 get + 6 delete |
| `registry-create-tools.json` | 9 create |
| `registry-update-tools.json` | 12 update |
| `registry-people-tools.json` | 8 student / membership / enrolment verbs |
| `registry-binding-publishing-tools.json` | 8 binding, publishing, OAuth |

## The findings that change implementation

**Eight list tools have no pagination at all** — `list_courses`, `list_lessons`, `list_quizzes`,
`list_questions`, `list_question_banks`, `list_web_packages`, `list_course_ratings`,
`list_quiz_question_bank_assignments`. The last is deliberate (a bounded set); the rest silently
truncate. These are the additive-compatibility targets.

**The 422 boundary.** Per-item isolation applies only *after* the envelope is parsed. Any
schema-level or cross-field violation on **any single item** is raised by Pydantic before the
handler runs and rejects the **whole request**. One bad row in a batch of fifty means nothing was
written — not forty-nine successes and one failure.

**Dedup is not uniform.** Creates are first-wins. Updates are last-write-wins — *except*
`update_groups` and `update_quiz_question_banks`, which are first-wins. There is no single rule.

**`anonymize_student` requires an `X-Confirm-Destructive: true` header**, separate from its OAuth
scope. A second, independent gate on the most destructive operation in the API.

**`update_lessons.content_items` is a tri-state.** Omitted leaves children untouched; a non-empty
array diffs and reorders; an **empty array deletes every child**. One field, three meanings, and
the destructive one is the easiest to send by accident.

**Re-binding a question bank is a partial update.** Fields omitted on re-bind are *preserved*, not
reset to defaults — and an omitted `order` is not re-derived.

**Answers are immutable on question update.** Changing them means delete and recreate.

**`create_web_packages` is asynchronous.** It returns rows in `PROCESSING`; a malformed archive
surfaces later as `state=ERROR`, never as an error on the create response.

**Naming asymmetries to reproduce exactly** (ADR-006): `get_signup_field_value` takes
`signup_field_value_id` while every other getter takes `id`; `create_signup_field_values` keys
items by the signup *field* id while `update_signup_field_values` keys them by the *value* id.

## Refreshing

Not automatable while the registry needs an interactive login. `scripts/check_upstream.py` will
diff against `tool-names.json` when credentials permit, and report the check as **skipped** —
never as passed — when they do not.
