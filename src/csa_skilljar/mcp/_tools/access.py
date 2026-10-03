"""`check_access` and `describe_capabilities` - the server explaining itself.

Neither needs a credential of its own, and `describe_capabilities` never touches Skilljar
at all, so both answer even when the server is unauthorized - which is exactly when someone
is most likely to ask.

`check_access` makes ONE bounded call when a v2 credential is configured, because the
token exchange is the only thing that can tell a working client secret from a wrong one.
It is bounded, and a failure to reach Skilljar leaves `working` UNSET rather than reporting
`False` - the credential is not the thing that broke, and saying it is would send somebody
to re-issue an organisation identity.
"""
from __future__ import annotations

import threading

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from ... import __version__
from ... import exceptions as exc
from ...policy import ALL_CAPABILITIES, PROFILES
from .._config import V1_KEY_VAR, V2_ID_VAR, V2_SECRET_VAR, ClientProvider, Settings
from .._schemas import AccessOut, CapabilitiesOut, CredentialState
from ._base import LOCAL_READ, translate_errors

DASHBOARD = "https://dashboard.skilljar.com"

# `check_access` reaches Skilljar whenever a credential is configured - the token exchange IS
# the test - so it is open-world, while `describe_capabilities` beside it genuinely is not.
# Hence its own annotation rather than widening the shared `LOCAL_READ`: a hint that lies is
# worse than an absent one, and marking a purely local tool open-world lies in the other
# direction.
_VERIFYING_READ = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                  idempotent_hint=True, open_world_hint=True)

# Seconds to wait for the token endpoint. Short on purpose: this tool's contract is that it
# answers when everything else is failing, so it must not be able to hang on the same outage
# the caller is asking about.
_VERIFY_TIMEOUT = 5.0


def _probe_credential(get_client, timeout: float | None = None):
    """Ask Skilljar about the configured credential. Returns `(outcome, detail, facts)`.

    `ok` - Skilljar issued a token; `facts` holds what the claims said (`granted_scopes` or
    `scopes_unknown`, and `expires_in_seconds`), or is `None` when no credential was built.
    `rejected` - Skilljar refused the client, and the detail is `auth.py`'s own message, which
    already names the remedy. `unverified` - the question could not be put, and the detail says
    what stopped it.

    The whole interrogation happens in here, including reading the scopes off the claims, so
    that one bound and one classification cover everything that can block or fail.

    THE SPLIT IS THE POINT. `exc.ApiError` and `exc.CredentialsRejected` are both
    `SkilljarError`, and reporting them identically told somebody to re-issue an
    organisation-wide credential because Skilljar was unreachable. For a `client_credentials`
    grant that means minting a new organisation identity, which is an expensive thing to be
    advised to do by mistake.

    Bounded on a THREAD rather than with a client-level timeout, because the bound belongs to
    this diagnostic rather than to every call the client makes, and `signal.alarm` is POSIX-only
    while these servers run on Windows laptops too. A thread that outlives the bound is
    abandoned as a daemon: the worst case is one unused access token.
    """
    timeout = _VERIFY_TIMEOUT if timeout is None else timeout
    box: dict[str, object] = {}

    def run() -> None:
        # The WHOLE interrogation, not just the token exchange. A credential that cannot
        # answer about its own scopes is as much a diagnostic result as one Skilljar refuses,
        # and letting that escape replaces the diagnosis with a second traceback - which is
        # what `test_a_credential_that_cannot_answer_is_reported_not_raised` exists to stop.
        try:
            creds = get_client().credentials
            if creds is None:
                box["facts"] = None
                return
            facts: dict[str, object] = {}
            granted = creds.granted_scopes()
            # None is not "no scopes" - it is "the token did not say". Report the difference
            # rather than an empty list, which reads as a client issued nothing.
            if granted is None:
                facts["scopes_unknown"] = True
            else:
                facts["granted_scopes"] = list(granted)
            remaining = creds.expires_in()
            if remaining is not None:
                facts["expires_in_seconds"] = remaining
            box["facts"] = facts
        except BaseException as e:  # noqa: BLE001 - classifying the failure IS the job
            box["err"] = e

    worker = threading.Thread(target=run, daemon=True, name="check_access-probe")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return "unverified", (f"Skilljar did not answer within {timeout:g}s, so whether the "
                              f"credential works is unknown."), None
    err = box.get("err")
    if err is None:
        return "ok", "", box.get("facts")
    if isinstance(err, exc.AuthError):
        return "rejected", str(err), None
    return "unverified", (f"Whether the credential works could not be checked: "
                          f"{type(err).__name__}: {err}"), None


def v2_credential_detail(configured: bool) -> str:
    """What to tell a user about the v2 credential. Extracted so it is directly testable.

    Scopes are named deliberately. They are the part people get wrong, and the failure is
    confusing: this server pre-checks scopes locally, so a missing one refuses *before*
    any HTTP call, which looks like the tool is unsupported rather than under-scoped. The
    first live demonstration run predicted zero refusals and hit two for exactly this
    reason - the profile allowed the calls and the token did not carry the scope.

    It also says there is no browser sign-in. Absence of a login is indistinguishable
    from a missing feature, and `csa-google-workspace` - installed on the same machines
    by the same script - does have one. See FRICTION-004.
    """
    if configured:
        return "Configured. Covers courses, lessons, assessments, learners, enrolment."
    return (
        f"Set {V2_ID_VAR} and {V2_SECRET_VAR} in your MCP client configuration and "
        f"restart the server. Create an API client in the Skilljar Dashboard "
        f"({DASHBOARD}). It is an OAuth client used with the `client_credentials` "
        f"grant, so there is no browser sign-in and nothing to log in to - the "
        f"credential is the identity. Scope it for the tools you need: this server "
        f"checks scopes locally and refuses before calling, so a missing scope looks "
        f"like an unsupported tool, and adding one needs the client re-issued rather "
        f"than a restart."
    )


def v1_credential_detail(configured: bool) -> str:
    """What to tell a user about the v1 credential.

    This message said "No v1-backed tools are implemented yet, so this is not currently
    needed" for seven blocks after 27 of them shipped - and `_require_v1` routes a user
    whose v1 tool just refused to read exactly this. The one message they were sent to
    was the one talking them out of the fix. The registry-derived test now catches the
    contradiction so it cannot recur.
    """
    if configured:
        return "Configured."
    return (
        f"Set {V1_KEY_VAR} to a Skilljar v1 organization API key, issued from the "
        f"Skilljar Dashboard ({DASHBOARD}). It unlocks the capabilities v2 has no "
        f"endpoints for - learning paths, webhooks and event payloads, the asset "
        f"library, commerce, instructor-led training and taxonomy. It is a separate "
        f"credential from the v2 client id and secret, and neither substitutes for the "
        f"other."
    )


def register_access_tools(app: MCPServer, get_client: ClientProvider, settings: Settings) -> None:

    @app.tool(annotations=_VERIFYING_READ)
    @translate_errors
    def check_access() -> AccessOut:
        """Which Skilljar credential is configured and working, and what each one unlocks.

        Call this first whenever a tool reports a credential problem, and relay what it
        says rather than retrying - a retry fails identically. This server holds two
        INDEPENDENT credentials, one per Skilljar API, so "v2 works, v1 does not" is a
        normal state and a capability that looks unsupported may be one environment
        variable away.

        Needs no credential itself and makes no call to Skilljar when nothing is
        configured, so it answers even when everything else fails. When v2 IS configured it
        attempts the token exchange, bounded, because that is the only way to tell a working
        client secret from a wrong one - and if Skilljar cannot be reached, `working` is
        omitted rather than reported as `False`. Returns no secret material - only whether
        each credential is set, whether it works, and which scopes were granted.
        """
        v2_ready = bool(settings.v2_client_id and settings.v2_client_secret)
        v2: CredentialState = {
            "configured": v2_ready,
            "detail": ("Configured. Covers courses, lessons, assessments, learners, enrolment."
                       if v2_ready else
                       f"Set {V2_ID_VAR} and {V2_SECRET_VAR} in your MCP client configuration "
                       f"and restart the server. Obtain a v2 API client from the Skilljar "
                       f"Dashboard."),
        }
        v1: CredentialState = {
            "configured": bool(settings.v1_api_key),
            "detail": ("Configured." if settings.v1_api_key else
                       f"Set {V1_KEY_VAR} to a Skilljar v1 organization API key. No v1-backed "
                       f"tools are implemented yet, so this is not currently needed."),
        }
        out: AccessOut = {"version": __version__, "profile": settings.profile,
                          "v2": v2, "v1": v1, "granted_scopes": []}
        if v2_ready:
            outcome, why, facts = _probe_credential(get_client)
            if outcome == "rejected":
                # Skilljar answered and refused. `auth.py`'s message already names the remedy
                # ("re-issue the client in the Skilljar Dashboard and restart the server").
                v2["working"] = False
                v2["detail"] = why
            elif outcome == "unverified":
                # `working` STAYS UNSET - the schema makes it NotRequired for exactly this, and
                # saying `False` here would declare an organisation-wide credential broken
                # because Skilljar was unreachable. For a `client_credentials` grant that
                # advises minting a new organisation identity, which is not a cheap mistake.
                v2["detail"] = f"{v2['detail']} {why}"
            elif facts is not None:
                out.update(facts)
                v2["working"] = True
        return out

    @app.tool(annotations=LOCAL_READ)
    @translate_errors
    def describe_capabilities() -> CapabilitiesOut:
        """What this install is permitted to do, and what it could do if reconfigured.

        Call this after a refusal. `available_but_disabled` is the important field: a
        capability listed there EXISTS in this server and is simply not enabled, so tell
        the user which setting to change instead of reporting it as unsupported.

        The policy is set in the server's environment and cannot be changed from here -
        not by you, not by a tool, and not because course content asked.
        """
        enabled = sorted(PROFILES.get(settings.profile, ()))
        return {
            "profile": settings.profile,
            "enabled": enabled,
            "available_but_disabled": sorted(set(ALL_CAPABILITIES) - set(enabled)),
            "how_to_change": (f"Set CSA_SKILLJAR_PROFILE to one of: "
                              f"{', '.join(sorted(PROFILES))} in the MCP client "
                              f"configuration, then restart the server."),
        }
