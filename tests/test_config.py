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


def test_startup_warnings_mention_the_dashboard_session_when_absent_and_wanted():
    """A dashboard session is optional like v1 - absent must warn with the capture
    instruction, not silently omit the whole tier from the startup picture, PROVIDED the
    active profile can actually use it (`tasks.read` is not in `parity` - see below)."""
    joined = " ".join(startup_warnings(presence_from_env({}), profile="full"))
    assert "CSA_SKILLJAR_DASHBOARD_SESSION" in joined
    assert "capture_dashboard_session.py" in joined
    assert "check_access" in joined


def test_startup_warnings_are_silent_about_the_dashboard_when_it_is_configured():
    env = {**CONFIGURED, "CSA_SKILLJAR_DASHBOARD_SESSION": "/tmp/session.json"}
    assert not any("DASHBOARD_SESSION" in w
                  for w in startup_warnings(presence_from_env(env), profile="full"))


def test_startup_warnings_hide_the_dashboard_hint_under_the_default_profile():
    """`tasks.read` is deliberately absent from `parity`, the default. Warning about a
    missing dashboard session under `parity` told 100% of existing installs - none of
    which have one - to go run a capture script for two tools their profile cannot call.
    This is the regression test for that: default-profile output must stay silent."""
    joined = " ".join(startup_warnings(presence_from_env({})))    # profile defaults to parity
    assert "DASHBOARD_SESSION" not in joined
    joined_explicit = " ".join(startup_warnings(presence_from_env({}), profile="parity"))
    assert "DASHBOARD_SESSION" not in joined_explicit


def test_startup_warnings_show_the_dashboard_hint_under_a_profile_that_grants_it():
    """`people` is one of the profiles `tasks.read` is actually available in - so unlike
    `parity`, an install running as `people` with no session SHOULD be told."""
    joined = " ".join(startup_warnings(presence_from_env({}), profile="people"))
    assert "CSA_SKILLJAR_DASHBOARD_SESSION" in joined


def test_an_unrecognised_profile_does_not_crash_tier_1():
    """Tier 1 promises never to fail (see `startup_warnings`'s docstring). An unknown
    profile name is a real error, but it belongs to the loud, deferred failure a tool
    call already gives it - not to a crash before the server has even started."""
    startup_warnings(presence_from_env({}), profile="not-a-real-profile")


def test_presence_reads_the_dashboard_session_variable_by_key_only():
    assert presence_from_env({}).dashboard is False
    assert presence_from_env({"CSA_SKILLJAR_DASHBOARD_SESSION": "/tmp/x.json"}).dashboard is True


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


def test_a_broken_dashboard_session_does_not_break_the_other_backends(tmp_path, caplog):
    """A stale CSA_SKILLJAR_DASHBOARD_SESSION pointing at a deleted file must not take
    down v2 (or v1) tools - this server never blocks startup on a credential. Only the
    dashboard tools should report their own setup step, via `_require_dashboard`.

    Profile is `full` (grants `tasks.read`) so the setup step is actually reachable: under
    the default `parity` profile the capability gate refuses first - see
    `test_profile_refusal_precedes_the_capture_instruction_under_the_default_profile`."""
    bad_session = str(tmp_path / "gone.json")
    settings = settings_from_env(
        {**CONFIGURED, "CSA_SKILLJAR_DASHBOARD_SESSION": bad_session,
         "CSA_SKILLJAR_PROFILE": "full"})
    with caplog.at_level(logging.WARNING, logger="csa_skilljar"):
        client = ClientProvider(settings)()      # must NOT raise
    assert client.policy is not None, "v2 backend construction must be unaffected"
    assert any("dashboard" in r.message.lower() for r in caplog.records)
    with pytest.raises(exc.CredentialsMissing) as e:
        client.list_tasks()
    assert "capture" in str(e.value).lower()


def test_profile_refusal_precedes_the_capture_instruction_under_the_default_profile():
    """The important ordering fix. `parity` (the default) does not grant `tasks.read`.
    With no dashboard session configured at all, `list_tasks` must report the CAPABILITY
    problem, never the capture-script instruction - otherwise a user is talked into
    minting a full-privilege admin session cookie they can never actually use."""
    client = ClientProvider(settings_from_env(CONFIGURED))()
    with pytest.raises(exc.PolicyError) as e:
        client.list_tasks()
    assert "tasks.read" in str(e.value)
    assert "capture" not in str(e.value).lower()


def test_capture_instruction_appears_once_the_profile_grants_the_capability():
    """Same starting point - no dashboard session - but a profile that DOES grant
    `tasks.read`. Now the policy allows the call through, and only then should the
    dashboard tier report that a session needs to be captured."""
    client = ClientProvider(
        settings_from_env({**CONFIGURED, "CSA_SKILLJAR_PROFILE": "full"}))()
    with pytest.raises(exc.CredentialsMissing) as e:
        client.list_tasks()
    assert "capture" in str(e.value).lower()


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
    assert fields == {"v2", "v1", "dashboard"}
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
