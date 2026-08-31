import logging
import threading

import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.mcp._config import (
    ClientProvider,
    env_with_file,
    presence_from_env,
    settings_from_env,
    startup_warnings,
)

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
    joined = " ".join(startup_warnings(presence_from_env({})))
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in joined
    assert "check_access" in joined, "a warning must point at the tool that explains it"


def test_startup_warnings_are_silent_about_v2_when_it_is_configured():
    assert not any("V2_CLIENT_ID" in w for w in startup_warnings(presence_from_env(CONFIGURED)))


def test_startup_warnings_make_no_network_call(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("Tier 1 must not touch the network")

    monkeypatch.setattr(httpx.Client, "post", boom)
    monkeypatch.setattr(httpx.Client, "get", boom)
    startup_warnings(presence_from_env(CONFIGURED))


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


def test_startup_warnings_cannot_even_see_a_credential():
    """Structural, not behavioural: the warning path reads only whether variables are
    SET, never their values, and never sees `Settings` at all. CodeQL flagged two
    earlier designs - one passing secret-bearing Settings into a printed function, and
    one deriving booleans from the secret values, which it still treats as tainted."""
    import dataclasses

    from csa_skilljar.mcp._config import CredentialPresence

    fields = {f.name for f in dataclasses.fields(CredentialPresence)}
    assert fields == {"v2", "v1"}
    presence = presence_from_env(CONFIGURED)
    assert "sk-live-DEADBEEF" not in repr(presence)
    assert all("sk-live-DEADBEEF" not in w for w in startup_warnings(presence))


# ── CSA_SKILLJAR_ENV_FILE ─────────────────────────────────────────────────────
#
# The installers (csa-skilljar-setup.sh / .ps1) write the credential to a file with
# owner-only permissions and point the MCP registration at it by PATH, so a rotation is
# one file edit rather than re-registering on every desktop. That only works if the
# server honours the variable - it registers `csa-skilljar-mcp`, and `mcp-launch.sh`
# (which reads the file) is a repo script that is not shipped in the wheel at all.
#
# Before this, the installer wrote the file, announced "credential installed", and the
# server ignored it completely. The failure mode is the ZD-17 shape: everything reports
# success and nothing works.

def test_no_env_file_variable_leaves_the_environment_untouched():
    env = {"CSA_SKILLJAR_V2_CLIENT_ID": "from-env"}
    assert env_with_file(env) is env


def test_values_are_read_from_the_file(tmp_path):
    f = tmp_path / "skilljar.env"
    f.write_text("CSA_SKILLJAR_V2_CLIENT_ID=id-from-file\n"
                 "CSA_SKILLJAR_V2_CLIENT_SECRET=secret-from-file\n")
    merged = env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f)})
    settings = settings_from_env(merged)
    assert settings.v2_client_id == "id-from-file"
    assert settings.v2_client_secret == "secret-from-file"
    # presence must agree, or the startup warning contradicts the tools
    assert presence_from_env(merged).v2 is True


def test_an_exported_value_beats_the_file(tmp_path):
    """Matches mcp-launch.sh: an override must not require editing the file."""
    f = tmp_path / "skilljar.env"
    f.write_text("CSA_SKILLJAR_V2_CLIENT_ID=from-file\n")
    merged = env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f),
                            "CSA_SKILLJAR_V2_CLIENT_ID": "from-export"})
    assert settings_from_env(merged).v2_client_id == "from-export"


def test_only_our_own_variables_are_taken_from_the_file(tmp_path):
    """The file may be a general .env. Importing PATH or AWS_SECRET_ACCESS_KEY from it
    would be a privilege-escalation seam, not a convenience."""
    f = tmp_path / "skilljar.env"
    f.write_text("PATH=/evil\nAWS_SECRET_ACCESS_KEY=nope\nCSA_SKILLJAR_V1_API_KEY=ours\n")
    merged = env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f)})
    assert merged["CSA_SKILLJAR_V1_API_KEY"] == "ours"
    assert "AWS_SECRET_ACCESS_KEY" not in merged
    assert "PATH" not in merged


def test_quotes_and_comments_and_export_are_tolerated(tmp_path):
    f = tmp_path / "skilljar.env"
    f.write_text('# a comment\n\n'
                 'export CSA_SKILLJAR_V2_CLIENT_ID="quoted-id"\n'
                 "CSA_SKILLJAR_V1_API_KEY='single'\n")
    merged = env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f)})
    assert merged["CSA_SKILLJAR_V2_CLIENT_ID"] == "quoted-id"
    assert merged["CSA_SKILLJAR_V1_API_KEY"] == "single"


def test_a_missing_file_warns_and_does_not_stop_startup(tmp_path, caplog):
    missing = tmp_path / "absent.env"
    with caplog.at_level(logging.WARNING, logger="csa_skilljar"):
        merged = env_with_file({"CSA_SKILLJAR_ENV_FILE": str(missing)})
    assert merged == {"CSA_SKILLJAR_ENV_FILE": str(missing)}
    assert any("could not be read" in r.message for r in caplog.records)


def test_a_file_with_none_of_our_variables_says_so(tmp_path, caplog):
    """ZD-17. A credential file that yields nothing must not look identical to one that
    worked - that is exactly how the installer's 'credential installed' became a lie."""
    f = tmp_path / "skilljar.env"
    f.write_text("SOMETHING_ELSE=1\n")
    with caplog.at_level(logging.WARNING, logger="csa_skilljar"):
        env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f)})
    assert any("no CSA_SKILLJAR_" in r.message for r in caplog.records)


def test_the_file_contents_never_reach_the_log(tmp_path, caplog):
    f = tmp_path / "skilljar.env"
    f.write_text("CSA_SKILLJAR_V2_CLIENT_SECRET=sk_live_TOPSECRET\n")
    with caplog.at_level(logging.DEBUG, logger="csa_skilljar"):
        env_with_file({"CSA_SKILLJAR_ENV_FILE": str(f)})
    assert not any("sk_live_TOPSECRET" in r.getMessage() for r in caplog.records)
