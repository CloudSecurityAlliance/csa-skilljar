# FRICTION-005: I wrote a test that could not fail, then made the same mistake fixing it

**Status:** Resolved
**Date identified:** 2026-09-28
**Date resolved:** 2026-09-28
**Type:** AI-inefficient

## Description

During the climb from 93% to 100% coverage I wrote `test_fake_filters_actually_filter.py`
as a **census**: derive every filter on `FakeBackend` from the signatures, assert for each
that an impossible value returns no rows. Forty parametrised cases, each named after its
filter. It looked like a settled question.

It ran against `FakeBackend(**CONTAINERS)`, which seeds **one** collection. So for **38 of
the 40** the *unfiltered* call already returned `[]`, and every assertion held because there
was nothing to return rather than because the filter worked. It was hiding ten filters the
double accepted and silently ignored — including `get_course_analytics`, which answered a
question about a course that does not exist with a confident enrolment count.

Then, fixing it, I made the neighbouring mistake **twice more**:

1. The membership rule skipped every parameter without a default — the definition of
   "optional filter", and obviously correct — which excluded **required selectors**, the
   worst case in the population. A required selector that is ignored does not return too
   much; it returns another parent's rows under the name of the one you asked for.
2. The loop named one class, `FakeBackend`, and there are **two** backends. Three filters on
   `FakeV1Backend` were in the signature with no filtering code at all (#105).

Three occurrences, one session, same shape each time.

## Why this is worth logging rather than dismissing

**A census is more dangerous than the hand-written tests it replaces, not less.** That is
the opposite of why I reached for it. Forty green ticks with the filter names in them read
as thorough, and nobody re-reads a loop that produced forty passes — which is exactly the
appearance the two defects sat under.

It also cost real rework: each of the three was found by measuring rather than by a failing
test, and the second and third were found only because the first made me suspicious enough
to look again. Had I stopped after the first fix, two of the three would still be there.

## Attention tax

Low per occurrence and badly distributed. Writing the census was fast; discovering it was
decorative took a deliberate measurement nothing prompted. The cost lands entirely on
whoever eventually trusts the green result — which in a coverage climb is the next person to
assume that area is covered.

## The generalisable half

The failure is **never in the assertions**, which is where review attention goes. It is in
the two things the census derives:

- **the set** — a predicate written from the typical member excludes the atypical one, and
  the atypical one is where the defects are
- **the baseline** — deriving membership gets every member enumerated for free, and says
  nothing about whether any case *can* fail

Those are different properties and only the first is free.

## Resolution

Fixed in [#103](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/103) and
[#105](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/105): every collection
seeded, membership widened to required selectors and to both backends, and — the durable
part — **a potency guard per filter, by name**, asserting the unfiltered call returns rows.
A collection that stops being seeded now fails there instead of quietly draining its case of
meaning. Both censuses were then mutation-tested, per CLAUDE.md's rule that a check which
cannot fail is theatre; that rule existed and I had not applied it to the census itself.

Generalised out of this project as
[`insights/a-census-proves-only-what-its-membership-rule-admits.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-census-proves-only-what-its-membership-rule-admits.md)
in CINO-Platform-Engineering, because the shape is not specific to tests — an allowlist, a
dashboard query and a scheduled report over "all open items" are all membership rules
written once from the typical member and never revisited.

## Related

- `CLAUDE.md` — "A check that cannot fail is theatre", and the census guidance added with this
- [#102](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/102),
  [#104](https://github.com/CloudSecurityAlliance/csa-skilljar/issues/104) — the two defects
  censuses *did* catch, which is why the shape is worth keeping rather than abandoning
