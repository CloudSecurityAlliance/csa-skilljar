"""v2 authentication: the `client_credentials` grant.

We use `client_credentials`, which Skilljar's own MCP server cannot: it is remote and
acts for a browser user, so its authorization server offers only `authorization_code`.
Running locally removes the browser, the redirect URI, the consent flow and the token
file entirely (ADR-003). The only cached state is an access token held in memory.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import httpx

from . import exceptions as exc

log = logging.getLogger(__name__)

TOKEN_PATH = "/v2/auth/token"          # nosec B105 # a URL path, not a secret
_REFRESH_MARGIN_SECONDS = 60.0
_FALLBACK_LIFETIME_SECONDS = 300.0     # used only when neither the JWT nor the server says


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
    except Exception as e:       # noqa: BLE001 - a malformed token must not crash startup
        # ZD-1: not swallowed. Returning {} silently made "no claims" and "not a JWT"
        # indistinguishable, and the caller loses both expiry and scope pre-checks.
        log.warning("v2 access token could not be decoded (%s); scope pre-checks and "
                    "expiry reporting are unavailable for this token", type(e).__name__)
        return {}
    if not isinstance(claims, dict):
        log.warning("v2 access token could not be decoded (payload is %s, not an object); "
                    "scope pre-checks and expiry reporting are unavailable",
                    type(claims).__name__)
        return {}
    return claims


class V2Credentials:
    """Holds the client id/secret and mints short-lived access tokens on demand."""

    def __init__(self, client_id: str, client_secret: str, *,
                 base_url: str = "https://api.skilljar.com",
                 http: httpx.Client | None = None) -> None:
        self._id = client_id; self._secret = client_secret
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)
        self._token: str | None = None; self._claims: dict[str, Any] = {}
        self._expiry: float | None = None

    def __repr__(self) -> str:      # never let a credential reach a log line
        return f"<V2Credentials client_id={self._id[:4]}... credential=***>"

    def _expired(self) -> bool:
        # ZD-17: an absorbing state lived here. When the JWT carried no usable `exp`
        # this returned True forever, so every call re-granted a token - correct code,
        # false premise, and nothing would ever report it. `_expiry` is now always set
        # from the best available source, so the cache always works.
        if self._expiry is None:
            return True
        return time.time() >= self._expiry - _REFRESH_MARGIN_SECONDS

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
        try:
            body = r.json()
        except ValueError as e:
            raise exc.ApiError("token grant returned a response that is not JSON") from e
        if not isinstance(body, dict):
            raise exc.ApiError("token grant returned JSON that is not an object")
        tok = body.get("access_token")
        if not tok:
            raise exc.ApiError("token grant returned no access_token")
        self._token = str(tok); self._claims = decode_claims(self._token)
        self._expiry = self._resolve_expiry(body.get("expires_in"))
        return self._token

    def _resolve_expiry(self, expires_in: Any) -> float:
        """Best available expiry, in this order: the JWT's `exp`, the grant response's
        `expires_in`, then a short conservative window. Never None - see `_expired`."""
        exp = self._claims.get("exp")
        if isinstance(exp, (int, float)):
            return float(exp)
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            return time.time() + float(expires_in)
        log.warning("v2 token carries no expiry and the grant response gave none; "
                    "assuming %.0fs", _FALLBACK_LIFETIME_SECONDS)
        return time.time() + _FALLBACK_LIFETIME_SECONDS

    def granted_scopes(self) -> tuple[str, ...] | None:
        """The scopes this token carries, or None when the token does not say.

        None and () are DIFFERENT and the caller must treat them differently. () means
        "issued with no scopes", which is a real answer and a reason to refuse locally.
        None means "this token has no scope claim we recognise", which says nothing
        about what the client may do - refusing on it would send the operator off to
        re-issue a credential that is fine.

        Skilljar issues `scopes` as a JSON LIST. RFC 6749 and RFC 9068 specify `scope`
        as a space-delimited STRING. Both are read, because this code originally read
        only the standard one and every single call was refused against a real token
        that was correctly scoped - the claim was there, under the other name, in the
        other shape.
        """
        self.token()
        for key in ("scopes", "scope"):
            if key not in self._claims:
                continue
            raw = self._claims[key]
            if isinstance(raw, (list, tuple)):
                return tuple(str(s) for s in raw if str(s))
            return tuple(s for s in str(raw).replace(",", " ").split() if s)
        # ZD-1/ZD-17: an absorbing state that quietly refuses everything is exactly the
        # shape of the `_expired` bug. Say so, once, and let the caller decide.
        log.warning(
            "v2 token carries no recognised scope claim (looked for `scopes` and "
            "`scope`; token has: %s). The local scope pre-check is disabled for this "
            "token - Skilljar remains authoritative and will reject anything the "
            "client may not do.", ", ".join(sorted(self._claims)) or "(no claims)")
        return None

    def expires_in(self) -> float | None:
        """Seconds until expiry, from cached state. No network call."""
        return None if self._expiry is None else self._expiry - time.time()

    def require_scope(self, scope: str) -> None:
        """Refuse locally, before any request, naming the exact missing scope."""
        granted = self.granted_scopes()
        if granted is None:
            # The token does not say what it may do. granted_scopes() has already
            # warned. Refusing here would be a guess presented as a fact, and would
            # send the operator to re-issue a credential that may be perfectly good.
            return
        if scope in granted:
            return
        raise exc.ScopeError(
            f"Your v2 client was issued: {', '.join(granted) or '(none)'}. Re-issue it "
            f"including `{scope}`, then restart the server. No call was made to Skilljar.",
            required=scope, granted=granted)
