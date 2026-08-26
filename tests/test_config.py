import threading

import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.mcp._config import ClientProvider, settings_from_env, startup_warnings

CONFIGURED = {"CSA_SKILLJAR_V2_CLIENT_ID": "cid", "CSA_SKILLJAR_V2_CLIENT_SECRET": "sk-live-DEADBEEF"}


def test_settings_read_from_env():
    s = settings_from_env({**CONFIGURED, "CSA_SKILLJAR_PROFILE": "authoring"})
    assert s.v2_client_id == "cid"
    assert s.profile == "authoring"
    assert s.v1_api_key is None


def test_profile_defaults_to_parity():
    assert settings_from_env({}).profile == "parity"


def test_settings_repr_never_leaks_a_credential():
    s = settings_from_env(CONFIGURED)
    assert "sk-live-DEADBEEF" not in repr(s)
    assert "set" in repr(s)


def test_startup_warnings_name_the_missing_credential_and_what_still_works():
    joined = " ".join(startup_warnings(settings_from_env({})))
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in joined
    assert "check_access" in joined, "a warning must point at the tool that explains it"


def test_startup_warnings_are_silent_about_v2_when_it_is_configured():
    s = settings_from_env(CONFIGURED)
    assert not any("V2_CLIENT_ID" in w for w in startup_warnings(s))


def test_startup_warnings_make_no_network_call(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("Tier 1 must not touch the network")

    monkeypatch.setattr(httpx.Client, "post", boom)
    monkeypatch.setattr(httpx.Client, "get", boom)
    startup_warnings(settings_from_env(CONFIGURED))


def test_provider_without_credentials_raises_only_when_called():
    provider = ClientProvider(settings_from_env({}))   # must NOT raise here
    with pytest.raises(exc.CredentialsMissing) as e:
        provider()
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in str(e.value)


def test_provider_construction_makes_no_network_call(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("constructing the provider must not touch the network")

    monkeypatch.setattr(httpx.Client, "post", boom)
    ClientProvider(settings_from_env(CONFIGURED))


def test_provider_is_thread_local():
    """Compare the objects, not id(). A thread's local storage is released when the
    thread ends, so the first client can be collected and the second can be handed
    the same id() - which made an earlier version of this test flaky. Holding the
    references keeps both alive and tests identity for real."""
    p = ClientProvider(settings_from_env(CONFIGURED))
    seen = []

    def grab():
        seen.append(p())

    t1 = threading.Thread(target=grab); t2 = threading.Thread(target=grab)
    t1.start(); t2.start(); t1.join(); t2.join()
    assert seen[0] is not seen[1], "sync handlers run on worker threads; each needs its own client"


def test_provider_reuses_one_client_within_a_thread():
    p = ClientProvider(settings_from_env(CONFIGURED))
    assert p() is p()


def test_client_exposes_the_policy_for_inspection():
    from csa_skilljar.policy import PROFILES
    p = ClientProvider(settings_from_env({**CONFIGURED, "CSA_SKILLJAR_PROFILE": "authoring"}))
    assert p().policy is not None
    assert p().policy.capabilities == frozenset(PROFILES["authoring"])
