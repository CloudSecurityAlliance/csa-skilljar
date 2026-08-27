# WAITING-FOR-003: A safe place to test writes against Skilljar

**Status:** Open
**Date identified:** 2026-08-27
**Type:** Person/Response — Hannah, on how testing is done in Skilljar

## Waiting for

An answer to: **where can this project write?** Concretely, one of —

- a Skilljar sandbox or staging organization, or
- a convention for disposable fixture objects inside the production organization
  (a naming prefix, a domain that is never published, a category reserved for tests),
  along with who cleans them up and how a stray one is recognised.

## Why waiting

Every write tool in this project is implemented and tested against `FakeBackend`. None
has ever run against Skilljar, and **none may until this is answered.**

The only organization these credentials reach is CSA's production one, with **42,669
real learners** in it. The failure modes are not subtle:

- `publish_courses` / `unpublish_published_course` change what anonymous visitors to a
  customer-facing site can see, immediately.
- `create_courses` and `create_lessons` leave content that someone has to find and
  delete, and a half-built course in a live catalogue is a support ticket.
- `delete_groups` is a hard delete that cascades to memberships and course-visibility
  overrides — learners lose access.
- `update_students` and the destructive people tools touch real named individuals.

A fake is always more permissive than reality, so the value of a live write test is
real. It is just not worth one production incident.

## Current position — writes are OFF, and enforced

Not a convention, a control. Three independent layers, each of which alone would stop
a write:

1. **The integration suite refuses to make one.** `tests/integration/conftest.py` wraps
   the live client in `ReadOnlyClient`, which is **fail-closed**: a method absent from a
   hand-written read-only allowlist raises `WouldHaveWritten` before anything reaches
   the network. A new tool is refused by default. Verified by adding a rogue test that
   calls `create_courses` and watching it fail.
2. **The default profile cannot reach most writes.** `parity` grants only the `*.read`
   capabilities.
3. **The credential is narrowly scoped.** The issued client holds 17 scopes and no
   `students:write`, `published-courses:write`, `student-groups:write` or
   `web-packages:write`, so the scope pre-check refuses those locally, with no request.

**The gap in layer 3, worth knowing:** the client *does* hold `courses:write`,
`lessons:write`, `quizzes:write` and `question-banks:write`. Authoring writes to the
production organization are technically possible with this credential. Layers 1 and 2
are what stop them.

**Suggested interim step:** re-issue the development client read-only — drop the four
`*:write` scopes — until this is answered. Nothing currently needs them, and it removes
the last path rather than guarding it. Costs one dashboard visit; reversible.

## Trigger

Hannah confirms where writes may go, and either:

- credentials for a sandbox/staging organization exist, **or**
- a fixture convention is written down here, with a cleanup owner named.

Then: `WAITING-FOR-003` closes, the write half of `tests/integration/` can be built, and
`READ_ONLY_METHODS` stops being the whole story.

## Questions for Hannah

1. Is there a Skilljar sandbox, staging, or trial organization CSA can use?
2. If not, is creating throwaway courses/lessons/quizzes in production acceptable given
   a naming convention, and what should that convention be?
3. Is there a domain that is never published, so a test course can be published to
   something no learner can reach?
4. How does CSA currently test Skilljar changes — is there an existing practice this
   should follow rather than invent?
5. Who should own cleanup, and how would a stray test object be spotted?

## Notes

Not blocking anything shipped: the write tools are complete, tested against the fake,
and their behaviour is pinned by the captured official registry. This blocks
*confidence*, not delivery — which is the honest way round, and worth saying so the
absence of live write tests is not mistaken for an absence of testing.
