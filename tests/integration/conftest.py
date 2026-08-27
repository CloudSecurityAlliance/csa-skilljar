"""Live Skilljar. Skipped unless CSA_SKILLJAR_INTEGRATION=1.

This is the fake/real seam guard. A fake is always more permissive than reality - a
soft-deleted-comment-shaped bug survived 660 green tests in csa-google-workspace for
exactly that reason. Behaviour only `V2Backend` has (opaque cursors, upstream error
translation, the 422 boundary) is not provable against `FakeBackend`.

Everything here is READ-ONLY. Nothing in this directory writes to a real organization.
"""
from __future__ import annotations

import os
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    """Skip ONLY the tests in this directory.

    `pytest_collection_modifyitems` is a session hook: even declared in a subdirectory
    conftest it receives EVERY collected item. Marking them all skipped this way turned
    a 216-test suite into "227 skipped" while every gate still reported OK - which is
    ZD-17 exactly, an absence-shaped failure that no error-shaped check can see.
    """
    if os.environ.get("CSA_SKILLJAR_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="set CSA_SKILLJAR_INTEGRATION=1 to run against real Skilljar")
    for item in items:
        if HERE in pathlib.Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def live_client():
    from csa_skilljar.mcp._config import ClientProvider, settings_from_env
    settings = settings_from_env(os.environ)
    if not (settings.v2_client_id and settings.v2_client_secret):
        pytest.skip("CSA_SKILLJAR_V2_CLIENT_ID / _SECRET not set")
    return ClientProvider(settings)()
