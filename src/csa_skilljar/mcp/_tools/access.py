"""`check_access` and `describe_capabilities` - the server explaining itself.

Neither needs a credential and neither touches Skilljar, so both answer even when the
server is unauthorized - which is exactly when someone is most likely to ask.
"""
from __future__ import annotations

from mcp.server import MCPServer

from ... import __version__
from ... import exceptions as exc
from ...policy import ALL_CAPABILITIES, PROFILES
from .._config import V1_KEY_VAR, V2_ID_VAR, V2_SECRET_VAR, ClientProvider, Settings
from .._schemas import AccessOut, CapabilitiesOut, CredentialState
from ._base import READ, translate_errors

DASHBOARD = "https://dashboard.skilljar.com"


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

    @app.tool(annotations=READ)
    @translate_errors
    def check_access() -> AccessOut:
        """Which Skilljar credential is configured and working, and what each one unlocks.

        Call this first whenever a tool reports a credential problem, and relay what it
        says rather than retrying - a retry fails identically. This server holds two
        INDEPENDENT credentials, one per Skilljar API, so "v2 works, v1 does not" is a
        normal state and a capability that looks unsupported may be one environment
        variable away.

        Needs no credential itself and makes no call to Skilljar when nothing is
        configured, so it answers even when everything else fails. Returns no secret
        material - only whether each credential is set, and which scopes were granted.
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
            try:
                creds = get_client().credentials
                if creds is not None:
                    granted = creds.granted_scopes()
                    # None is not "no scopes" - it is "the token did not say". Report
                    # the difference rather than showing an empty list, which reads as
                    # a client that was issued nothing.
                    if granted is None:
                        out["scopes_unknown"] = True
                    else:
                        out["granted_scopes"] = list(granted)
                    remaining = creds.expires_in()
                    if remaining is not None:
                        out["expires_in_seconds"] = remaining
                    v2["working"] = True
            except exc.SkilljarError as e:
                v2["working"] = False; v2["detail"] = str(e)
        return out

    @app.tool(annotations=READ)
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
