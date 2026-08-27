"""The 207 batch envelope, which every write in this block and every later block uses.

A partial failure must reach the caller per item. Collapsing it into one error is the
whole failure mode this shape exists to prevent.
"""
import pytest

from csa_skilljar.backend import parse_batch


def test_all_succeeded():
    out = parse_batch({
        "data": [{"status": "created", "id": "c1"}, {"status": "created", "id": "c2"}],
        "summary": {"total": 2, "succeeded": 2, "failed": 0},
    })
    assert out["total"] == 2
    assert len(out["succeeded"]) == 2
    assert out["failed"] == []


def test_partial_failure_keeps_both_sides():
    out = parse_batch({
        "data": [
            {"status": "created", "id": "c1"},
            {"status": "error", "code": "not_found", "detail": "no such course",
             "source": {"pointer": "/data/1/id"}},
        ],
        "summary": {"total": 2, "succeeded": 1, "failed": 1},
    })
    assert len(out["succeeded"]) == 1
    assert len(out["failed"]) == 1
    assert out["failed"][0]["code"] == "not_found"
    assert out["failed"][0]["pointer"] == "/data/1/id"


def test_summary_invariant_is_checked_not_trusted():
    """Skilljar documents succeeded + failed == total and enforces it server-side.
    Verify rather than trust: a mismatch means we are misreading the envelope, and
    silently reporting a wrong count is worse than failing."""
    with pytest.raises(ValueError, match="summary"):
        parse_batch({
            "data": [{"status": "created", "id": "c1"}],
            "summary": {"total": 5, "succeeded": 1, "failed": 1},
        })


def test_a_missing_summary_is_an_error_not_a_default():
    with pytest.raises(ValueError, match="summary"):
        parse_batch({"data": []})


def test_an_error_item_missing_its_pointer_still_parses():
    """Defensive: the pointer is how a caller correlates a failure to the row they
    sent, but a missing one must not crash the whole parse."""
    out = parse_batch({
        "data": [{"status": "error", "code": "validation_error", "detail": "bad"}],
        "summary": {"total": 1, "succeeded": 0, "failed": 1},
    })
    assert out["failed"][0]["pointer"] == ""
    assert out["failed"][0]["code"] == "validation_error"
