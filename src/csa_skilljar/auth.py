"""v2 authentication: the `client_credentials` grant.

We use `client_credentials`, which Skilljar's own MCP server cannot: it is remote and
acts for a browser user, so its authorization server offers only `authorization_code`.
Running locally removes the browser, the redirect URI, the consent flow and the token
file entirely (ADR-003). The only cached state is an access token held in memory.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from . import exceptions as exc

TOKEN_PATH = "/v2/auth/token"          # nosec B105 - a URL path, not a secret
_REFRESH_MARGIN_SECONDS = 60.0


def decode_claims(token: str) -> dict[str, Any]:
    """Read a JWT's claims WITHOUT verifying the signature.

    Deliberate: this is our own token and the server verifies it. We read `exp` and
    `scope` locally so `check_access` can report expiry and the scope pre-check can
    refuse an impossible call with zero network traffic. Never treat the result as
    an authorization decision about someone else's token.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:            # noqa: BLE001 - a malformed token must not crash startup
        return {}
    return claims if isinstance(claims, dict) else {}


class V2Credentials:
    """Holds the client id/secret and mints short-lived access tokens on demand."""

    def __init__(self, client_id: str, client_secret: str, *,
                 base_url: str = "https://api.skilljar.com",
                 http: httpx.Client | None = None) -> None:
        self._id = client_id; self._secret = client_secret
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)
        self._token: str | None = None; self._claims: dict[str, Any] = {}

    def __repr__(self) -> str:      # never let a credential reach a log line
        return f"<V2Credentials client_id={self._id[:4]}... credential=***>"

    def _expired(self) -> bool:
        exp = self._claims.get("exp")
        if not isinstance(exp, (int, float)):
            return True
        return time.time() >= float(exp) - _REFRESH_MARGIN_SECONDS

    def token(self) -> str:
        if self._token is not None and not self._expired():
            return self._token
        try:
            r = self._http.post(
                f"{self._base}{TOKEN_PATH}",
                data={"grant_type": "client_credentials",
                      "client_id": self._id, "client_secret": self._secret},
                headers={"Content-Type": "application/x-www-form-urlencoded"})
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach Skilljar to authenticate: {e}") from e
        if r.status_code in (400, 401, 403):
            raise exc.CredentialsRejected(
                "Skilljar rejected the v2 client credentials. They may have been rotated, or "
                "the client deleted. Re-issue the client in the Skilljar Dashboard and restart "
                "the server.")
        if r.status_code >= 400:
            raise exc.ApiError(f"token grant failed with HTTP {r.status_code}", status=r.status_code)
        tok = r.json().get("access_token")
        if not tok:
            raise exc.ApiError("token grant returned no access_token")
        self._token = str(tok); self._claims = decode_claims(self._token)
        return self._token

    def granted_scopes(self) -> tuple[str, ...]:
        self.token()
        raw = self._claims.get("scope") or ""
        return tuple(s for s in str(raw).replace(",", " ").split() if s)

    def expires_in(self) -> float | None:
        """Seconds until expiry, from the cached token's claims. No network call."""
        exp = self._claims.get("exp")
        return float(exp) - time.time() if isinstance(exp, (int, float)) else None

    def require_scope(self, scope: str) -> None:
        """Refuse locally, before any request, naming the exact missing scope."""
        granted = self.granted_scopes()
        if scope in granted:
            return
        raise exc.ScopeError(
            f"Your v2 client was issued: {', '.join(granted) or '(none)'}. Re-issue it "
            f"including `{scope}`, then restart the server. No call was made to Skilljar.",
            required=scope, granted=granted)
