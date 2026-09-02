"""The Skilljar dashboard — the third backend, and the one that owns least.

ADR-002 extended: **v2 -> v1 -> dashboard.** This tier owns only capabilities neither
API exposes, and is the first to be retired, not the last. See
`docs/superpowers/specs/2026-09-02-dashboard-backend-design.md`.

Two things make this unlike the API backends and both are load-bearing:

1. **The credential is a session cookie with no scopes.** v2's token carries 18 named
   scopes checked locally before a request leaves; this has nothing equivalent. The
   capability gate is therefore the entire perimeter, not one control among several.
2. **The endpoints are undocumented and unversioned.** There is no OpenAPI document to
   diff, so `scripts/check_dashboard.py` exists to detect drift that would otherwise
   surface as an empty task list - a queue looking clear when it is not.
"""
from __future__ import annotations

import json

from . import exceptions as exc

DEFAULT_BASE = "https://dashboard.skilljar.com"
SESSION_COOKIE = "sj_sessionid"          # nosec B105 # a cookie name, not a secret
_TIMEOUT = 30.0
_CAPTURE_HINT = ("Run `python scripts/capture_dashboard_session.py` and log in when the "
                 "browser opens. The login is captcha-protected, so a human has to do it.")


class DashboardSession:
    """Cookies from a human-established dashboard login.

    A BEARER credential with no scopes: it can do anything the logged-in user can. It is
    never narrowed by us, only by which dashboard role the account holds.
    """

    def __init__(self, cookies: dict[str, str]) -> None:
        if SESSION_COOKIE not in cookies:
            raise exc.CredentialsMissing(
                f"the dashboard session file has no `{SESSION_COOKIE}` cookie, so it is "
                f"not a logged-in session. {_CAPTURE_HINT}")
        self._cookies = dict(cookies)

    @classmethod
    def from_file(cls, path: str) -> DashboardSession:
        """Load a Playwright `storage_state` file.

        A missing or unreadable file is a CREDENTIAL problem, not an OSError. The
        difference matters at the tool boundary: `CredentialsMissing` carries a setup
        instruction, an OSError carries a stack trace.
        """
        try:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
        except OSError as e:
            raise exc.CredentialsMissing(
                f"could not read the dashboard session file ({type(e).__name__}). "
                f"{_CAPTURE_HINT}") from e
        except json.JSONDecodeError as e:
            raise exc.CredentialsMissing(
                f"the dashboard session file is not valid JSON. {_CAPTURE_HINT}") from e
        cookies = {c["name"]: c["value"] for c in blob.get("cookies", [])
                   if "skilljar" in c.get("domain", "")}
        return cls(cookies)

    def cookies(self) -> dict[str, str]:
        return dict(self._cookies)

    def __repr__(self) -> str:
        # Hand-written: embedders log clients, and a default repr here leaks a session
        # that can act as a dashboard administrator.
        return f"DashboardSession(cookies=<redacted, {len(self._cookies)} names>)"
