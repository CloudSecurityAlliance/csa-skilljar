"""The guard that keeps this suite off CSA's production organization.

Until there is a sandbox or a disposable fixture organization (WAITING-FOR-003), these
credentials reach the real one — 42,669 real learners. "Everything here is read-only"
was a docstring for several blocks; this is the version that can fail.
"""
import pytest

from csa_skilljar import policy as P

from .conftest import READ_ONLY_METHODS, ReadOnlyClient, WouldHaveWritten


class Spy:
    """Stands in for the live client and records anything that gets through."""

    def __init__(self):
        self.called = []

    def __getattr__(self, name):
        def record(**kwargs):
            self.called.append(name)
            return {"data": []}
        return record


@pytest.mark.parametrize("method", [
    "create_courses", "update_courses", "delete_quizzes", "anonymize_student",
    "set_student_password", "publish_courses", "delete_groups",
    "add_group_memberships", "bulk_enroll", "register_oauth_client",
])
def test_a_mutating_call_is_refused_before_it_reaches_the_client(method):
    spy = Spy()
    guarded = ReadOnlyClient(spy)
    with pytest.raises(WouldHaveWritten) as e:
        getattr(guarded, method)(items=[])
    assert method in str(e.value)
    assert "production" in str(e.value)
    assert spy.called == [], "the call reached the real client"


def test_reads_pass_through():
    spy = Spy()
    guarded = ReadOnlyClient(spy)
    guarded.list_courses(page_size=1)
    guarded.get_course(course_id="x")
    assert spy.called == ["list_courses", "get_course"]


def test_the_guard_is_fail_closed_for_a_method_it_has_never_heard_of():
    """A tool added next block is refused by default. The failure mode this prevents is
    an allowlist that quietly stops covering the surface it was written for."""
    guarded = ReadOnlyClient(Spy())
    with pytest.raises(WouldHaveWritten):
        # Written as a call because that is the mistake being prevented. The guard
        # actually fires on ATTRIBUTE ACCESS, so nothing reaches the network even if a
        # test builds arguments for it.
        guarded.some_tool_invented_next_month(anything="at all")


def test_every_read_only_method_is_a_real_backend_method():
    """Guards the guard, first direction: a typo in the list would silently refuse a
    legitimate read, and the test author would 'fix' it by loosening the guard."""
    unknown = sorted(READ_ONLY_METHODS - set(P._GATES))
    assert not unknown, f"READ_ONLY_METHODS names methods that do not exist: {unknown}"


def test_no_method_gated_by_a_write_capability_is_on_the_read_only_list():
    """Guards the guard, second direction, and this is the one that matters. The list is
    hand-written on purpose - deriving it from _GATES would make the control agree with
    any mislabelled gate rather than check it. This asserts the two AGREE without either
    being built from the other."""
    wrongly_allowed = sorted(
        m for m in READ_ONLY_METHODS
        if (cap := P._GATES.get(m)) and not cap.endswith(".read"))
    assert not wrongly_allowed, (
        f"these are on the read-only list but gated as writes: {wrongly_allowed}")


def test_every_read_gated_method_is_on_the_list():
    """The other direction: a read tool missing from the list is refused for no reason,
    which reads as a broken suite rather than a safety control doing its job."""
    missing = sorted(
        m for m, cap in P._GATES.items()
        if cap and cap.endswith(".read") and m not in READ_ONLY_METHODS)
    assert not missing, f"read-only methods absent from the allowlist: {missing}"


def test_the_live_fixture_is_actually_wrapped(live_client):
    """The control is only worth anything if the fixture every other test uses is the
    guarded one."""
    assert isinstance(live_client, ReadOnlyClient)
    with pytest.raises(WouldHaveWritten):
        live_client.create_courses(items=[{"title": "this must never be created"}])
