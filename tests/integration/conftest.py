"""Live Skilljar. Skipped unless CSA_SKILLJAR_INTEGRATION=1.

This is the fake/real seam guard. A fake is always more permissive than reality - a
soft-deleted-comment-shaped bug survived 660 green tests in csa-google-workspace for
exactly that reason. Behaviour only `V2Backend` has (opaque cursors, upstream error
translation, the 422 boundary) is not provable against `FakeBackend`.

Everything here is READ-ONLY. Nothing in this directory writes to a real organization.
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("CSA_SKILLJAR_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="set CSA_SKILLJAR_INTEGRATION=1 to run against real Skilljar")
    for item in items:
        item.add_marker(skip)


@pytest.fixture(scope="session")
def live_client():
    from csa_skilljar.mcp._config import ClientProvider, settings_from_env
    settings = settings_from_env(os.environ)
    if not (settings.v2_client_id and settings.v2_client_secret):
        pytest.skip("CSA_SKILLJAR_V2_CLIENT_ID / _SECRET not set")
    return ClientProvider(settings)()
