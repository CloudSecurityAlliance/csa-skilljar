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
                    out["granted_scopes"] = list(creds.granted_scopes())
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
