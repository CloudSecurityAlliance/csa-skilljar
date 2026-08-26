"""Shared fixtures and suite-wide guards."""
from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def no_unexpected_error_logs(caplog):
    """ZD-12: a test run produces two signals - did it pass, and did the system emit
    anything alarming while it ran? A green test that logged an ERROR is still a problem.

    Scoped to ERROR and above deliberately. Several tests here assert on WARNING output
    (an undecodable token, a missing expiry), so failing on WARNING would fire on correct
    behaviour - and ZD-2 is explicit that a check which alarms on correct behaviour gets
    muted, and a muted check is worse than no check.

    Opt out for a test that genuinely expects an ERROR:  @pytest.mark.expect_error_logs
    """
    caplog.set_level(logging.WARNING, logger="csa_skilljar")
    yield
    # get_records("call"), NOT .records: pytest clears caplog between the setup, call
    # and teardown phases, so in teardown `.records` is the teardown phase's records -
    # always empty. The first version of this fixture used `.records` and therefore
    # could never fail, which is exactly the decorative check this file warns about.
    errors = [r for r in caplog.get_records("call") if r.levelno >= logging.ERROR]
    assert not errors, (
        "test passed but logged ERROR-level records:\n  "
        + "\n  ".join(f"{r.name}: {r.getMessage()}" for r in errors)
    )


@pytest.fixture
def anyio_backend():
    """asyncio only. The server is stdio and the SDK runs on asyncio in practice;
    running the protocol tests under trio as well would test the SDK, not us."""
    return "asyncio"


def pytest_addoption(parser):
    parser.addoption("--cold-use", action="store_true", default=False,
                     help="run the model-in-the-loop description test")
