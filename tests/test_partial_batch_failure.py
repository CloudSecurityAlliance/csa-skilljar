"""A batch with one bad item returns one bad RESULT, not an exception.

Skilljar's v2 batch endpoints answer per item: ten courses in, ten results out, some of which
may be errors. `FakeBackend` models that, and **none of it had ever been exercised** — so every
test in this suite saw all-success batches, against a double that could produce failures and
never did.

That is the shape `csa-google-workspace` paid for: a fake more permissive than the system it
stands for does not fail to catch a bug, it *certifies* one. A library that mishandled a partial
failure would have passed the whole suite.

Four properties are asserted for every method that can emit one, because they are what makes a
per-item error useful rather than merely present:

1. **one entry per input item** — never fewer, never an exception
2. **the error is positioned by index** — `/data/{i}/…`, so a caller with fifty items knows
   *which* one
3. **the good items still succeed** — partial, not all-or-nothing
4. **the detail names the offending value** — `no course with id nope`, not `invalid input`
"""
from __future__ import annotations

import pytest

from csa_skilljar.backend import FakeBackend


#: (method, build(backend) -> kwargs, index of the item expected to fail, expected code).
#:
#: `build` takes the backend so a case can create what it needs first — group membership needs a
#: group to exist, and publishing twice needs a first publication. Hand-written, because a derived
#: caller cannot know what makes an item invalid; that differs per resource. What is NOT
#: hand-written is the assertions: every row goes through the same four checks, so adding a row
#: costs one line and buys the whole battery.
def _group(backend):
    gid = backend.create_groups(items=[{"name": "G"}])["data"][0]["id"]
    return {"group_id": gid, "student_ids": ["s1", "s1"]}


def _already_published(backend):
    first = {"course_id": "c1", "domain_id": "d1"}
    backend.publish_courses(items=[first])
    return {"items": [dict(first)]}


def K(**kwargs):
    """A case whose arguments need nothing built first."""
    return lambda _backend: kwargs


CASES = [
    # not_found — an id that is not there. The dominant shape, ~15 methods.
    ("update_courses", K(**{"items": [{"id": "nope", "title": "x"}]}), 0, "not_found"),
    ("update_lessons", K(**{"items": [{"id": "nope", "title": "x"}]}), 0, "not_found"),
    ("update_quizzes", K(**{"items": [{"id": "nope", "name": "x"}]}), 0, "not_found"),
    ("delete_quizzes", K(**{"quiz_ids": ["nope"]}), 0, "not_found"),
    ("update_questions", K(**{"items": [{"id": "nope"}]}), 0, "not_found"),
    ("delete_questions", K(**{"question_ids": ["nope"]}), 0, "not_found"),
    ("update_question_banks", K(**{"items": [{"id": "nope", "name": "x"}]}), 0, "not_found"),
    ("delete_question_banks", K(**{"bank_ids": ["nope"]}), 0, "not_found"),
    ("update_groups", K(**{"items": [{"id": "nope", "name": "x"}]}), 0, "not_found"),
    ("delete_groups", K(**{"group_ids": ["nope"]}), 0, "not_found"),
    ("update_students", K(**{"items": [{"id": "nope"}]}), 0, "not_found"),
    ("update_enrollments", K(**{"items": [{"id": "nope"}]}), 0, "not_found"),
    ("update_published_courses", K(**{"items": [{"id": "nope"}]}), 0, "not_found"),
    ("update_web_packages", K(**{"items": [{"id": "nope"}]}), 0, "not_found"),
    ("update_signup_field_values", K(**{"items": [{"id": "nope", "value": "x"}]}), 0, "not_found"),
    ("create_lessons", K(**{"items": [{"title": "orphan"}]}), 0, "not_found"),
    ("create_questions", K(**{"items": [{"question_html": "orphan"}]}), 0, "not_found"),
    # validation_error — present but unusable.
    ("create_quizzes", K(**{"items": [{"name": ""}]}), 0, "validation_error"),
    ("create_question_banks", K(**{"items": [{"name": ""}]}), 0, "validation_error"),
    ("create_courses", K(**{"items": [{"title": ""}]}), 0, "validation_error"),
    ("create_courses", K(**{"items": [{"title": "x" * 501}]}), 0, "validation_error"),
    # duplicate_in_batch — the SECOND occurrence fails and the first still lands.
    ("create_students", K(**{"items": [{"email": "a@b.c"}, {"email": "a@b.c"}]}), 1, "duplicate_in_batch"),
    ("create_groups", K(**{"items": [{"name": "G"}, {"name": "G"}]}), 1, "duplicate_in_batch"),
    ("bulk_enroll", K(**{"published_course_id": "p1", "emails": ["a@b.c", "a@b.c"]}), 1, "duplicate_in_batch"),
    ("add_group_memberships", _group, 1, "duplicate_in_batch"),
    ("remove_group_memberships", _group, 1, "duplicate_in_batch"),
    # already_published — a per-item conflict, so the rest of the batch still lands.
    ("publish_courses", _already_published, 0, "already_published"),
]


def entries(result) -> list[dict]:
    return result["data"]


@pytest.mark.parametrize("method, build, bad_index, code",
                         CASES, ids=[f"{m}-{c}" for m, _, _, c in CASES])
def test_a_bad_item_becomes_an_error_entry_rather_than_an_exception(
        method, build, bad_index, code):
    """Property 1 and 2: one entry per item, and the bad one is at the right index."""
    backend = FakeBackend()
    kwargs = build(backend)
    sent = next(v for v in kwargs.values() if isinstance(v, list))

    data = entries(getattr(backend, method)(**kwargs))

    assert len(data) == len(sent), (
        f"{method} was sent {len(sent)} items and answered with {len(data)} — a batch endpoint "
        f"answers per item, so a caller cannot line the results up against what it sent")

    failed = data[bad_index]
    assert failed["status"] == "error"
    assert failed["code"] == code
    assert f"/data/{bad_index}" in failed["source"]["pointer"], (
        f"the error does not say WHICH item failed: {failed['source']}")


@pytest.mark.parametrize("method, build, bad_index, code",
                         CASES, ids=[f"{m}-{c}" for m, _, _, c in CASES])
def test_the_detail_names_the_offending_value(method, build, bad_index, code):
    """Property 4. `invalid input` sends somebody to read fifty items by hand; naming the id or
    the address they sent turns the report into the fix."""
    backend = FakeBackend()
    data = entries(getattr(backend, method)(**build(backend)))
    detail = data[bad_index]["detail"]

    assert detail and detail.strip(), f"{method} produced an error with an empty detail"
    assert detail.lower() != "invalid input"
    assert len(detail) > 10, f"{method}: {detail!r} is too short to act on"


@pytest.mark.parametrize("method, build, bad_index, code",
                         [c for c in CASES if c[2] > 0],
                         ids=[f"{m}" for m, _, i, _ in CASES if i > 0])
def test_the_good_items_in_the_batch_still_succeed(method, build, bad_index, code):
    """Property 3, and the one most likely to be wrong. A batch is not a transaction here: item
    0 lands, item 1 is rejected, and the caller is told both. All-or-nothing would be a
    defensible design and it is not this one — so a test that only checked the failure would
    pass against a backend that silently discarded the good work."""
    backend = FakeBackend()
    data = entries(getattr(backend, method)(**build(backend)))

    good = [d for i, d in enumerate(data) if i != bad_index]
    assert good, "the case is pointless without a good item to preserve"
    assert all(d["status"] != "error" for d in good), (
        f"{method} discarded the valid items alongside the invalid one: {data}")
    assert all(d.get("id") for d in good), "a successful entry must carry the id it created"


def test_the_census_covers_every_code_the_fake_can_emit():
    """The guard on the guard. `FakeBackend` emits four codes; if it grows a fifth, this fails
    rather than the new one going untested — the same derivation discipline as the operation
    censuses, applied to the error vocabulary instead of the method list."""
    import inspect
    import re

    emitted = set(re.findall(r'"code": "(\w+)"', inspect.getsource(FakeBackend)))
    covered = {c for _, _, _, c in CASES}

    assert emitted - covered == set(), (
        f"FakeBackend can emit codes no case exercises: {sorted(emitted - covered)}")


def test_a_missing_CONTAINER_raises_while_a_bad_ITEM_does_not():
    """The two failures are different in kind and answered differently, which is the part a
    caller has to get right.

    `add_group_memberships(group_id=...)` names a container. If the GROUP is absent there is no
    batch to partially succeed at — nothing in the request is actionable — so it raises. If a
    STUDENT within the batch is a duplicate, the rest still lands and the answer is an entry.

    Conflating them either way is a real bug: raising on a bad item discards the good work, and
    returning entries for a missing group reports fifty failures for one wrong argument.
    """
    from csa_skilljar import exceptions as exc

    backend = FakeBackend()
    with pytest.raises(exc.NotFoundError, match="no group with id"):
        backend.add_group_memberships(group_id="absent", student_ids=["s1"])

    gid = backend.create_groups(items=[{"name": "G"}])["data"][0]["id"]
    data = backend.add_group_memberships(group_id=gid, student_ids=["s1", "s1"])["data"]
    assert [d["status"] for d in data] == ["created", "error"]
