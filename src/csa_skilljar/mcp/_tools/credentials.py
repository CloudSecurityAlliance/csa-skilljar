"""Credential administration — everything the official server omits.

Skilljar's own MCP server exposes `register_oauth_client`, the tool that MINTS a
credential, and withholds every tool that AUDITS or REMEDIATES one. You can create an
OAuth client through it and then cannot list what exists, see what a client may do,
narrow it, rotate a leaked secret, or turn it off.

This module is the second half. All of it is gated by `admin.credentials`, off in every
profile but `admin`, because a tool that can enumerate and rotate every credential in an
organization should not be on by default.

Two things here are counter-intuitive and both are upstream's design:

* `revoke_refresh_token` answers 200 whether or not the token existed. RFC 7009 §2.2
  specifies that, so the endpoint cannot be used to test whether a token is valid.
  Verified against live Skilljar with a deliberately invalid token.
* `DELETE /v2/clients/{id}` is titled "Deactivate client" upstream. It is not a deletion,
  and this module does not call it one.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import (
    OAuthClientListOut,
    OAuthClientOut,
    RevocationOut,
    ScopeCatalogueOut,
)
from ._base import DESTRUCTIVE, READ, WRITE, translate_errors

_CLIENT_KEYS = ("name", "description", "client_id", "is_active", "scope_codenames",
                "ip_allowlist", "created_at")
_UPDATE_FIELDS = frozenset({"name", "description", "scope_codenames", "scope_preset",
                            "ip_allowlist"})

_ONE_TIME = (
    "The client_secret in this response is shown ONCE and cannot be retrieved again — "
    "there is no endpoint that reads it back. Store it somewhere durable before doing "
    "anything else, and do not leave it in a chat transcript or a ticket.")
_LIST_NOTE = ("Secrets are never included in a listing; they exist only in the response "
              "that created or rotated them.")


def _flatten(row: dict[str, Any], *, with_secret: bool = False) -> OAuthClientOut:
    attrs = row.get("attributes", {})
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in _CLIENT_KEYS:
        if key in attrs:
            out[key] = attrs[key]
    if with_secret and attrs.get("client_secret"):
        out["client_secret"] = attrs["client_secret"]
        out["warning"] = _ONE_TIME
    return cast(OAuthClientOut, out)


def register_credential_tools(app: MCPServer,
                              get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_oauth_clients() -> OAuthClientListOut:
        """List the organization's API clients — who can reach this API and how.

        This is the audit tool Skilljar's own MCP server does not provide: it can create
        a client but cannot show you what exists. Use this to find credentials nobody
        remembers issuing, or to check what a client is scoped to before trusting it.

        Each row carries `is_active`, `scope_codenames` and `ip_allowlist`. NO SECRETS
        are returned — a client secret exists only in the response that created or
        rotated it, and there is no endpoint that reads it back.

        Not paginated: the client list is a small bounded set.

        Requires the `clients:read` OAuth scope, and the `admin` capability profile.
        """
        envelope = get_client().list_oauth_clients()
        return {"clients": [_flatten(r) for r in envelope.get("data", [])],
                "note": _LIST_NOTE}

    @app.tool(annotations=READ)
    @translate_errors
    def get_oauth_client(id: str) -> OAuthClientOut:
        """Inspect one API client: what it may do, and whether it still works.

        `id` is the client's record id from `list_oauth_clients`, not its `client_id`
        (the value used when authenticating). Both are on the row.

        `is_active` false means the client has been deactivated and can no longer obtain
        a token. `scope_codenames` is exactly what it may do; `ip_allowlist`, when
        non-empty, is where it may do it from.

        No secret is returned. There is no way to read one back.

        Requires the `clients:read` OAuth scope, and the `admin` capability profile.
        """
        return _flatten(get_client().get_oauth_client(client_id=id)["data"])

    @app.tool(annotations=READ)
    @translate_errors
    def list_oauth_scopes() -> ScopeCatalogueOut:
        """List every OAuth scope this API defines, and the named preset bundles.

        Read this BEFORE creating or narrowing a client — it is the authoritative list
        of what `scope_codenames` accepts, with a description and category for each, and
        it is what makes least-privilege possible rather than guesswork.

        `presets` are named bundles Skilljar maintains, usable as `scope_preset` instead
        of listing codenames one by one.

        The catalogue is served from in-memory constants upstream, so it reflects what
        the API defines, which is not necessarily what any given client was granted.

        Requires the `clients:read` OAuth scope, and the `admin` capability profile.
        """
        envelope = get_client().list_oauth_scopes()
        rows = envelope.get("data", [])
        return {"scopes": [{"codename": r.get("attributes", {}).get("codename", r.get("id", "")),
                            "description": r.get("attributes", {}).get("description", ""),
                            "category": r.get("attributes", {}).get("category", "")}
                           for r in rows],
                "presets": dict(envelope.get("meta", {}).get("presets", {})),
                "note": "What the API defines, not what any one client was granted. "
                        "Use get_oauth_client for that."}

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_oauth_client(name: str, description: str | None = None,
                            scope_codenames: list[str] | None = None,
                            scope_preset: str | None = None,
                            ip_allowlist: list[str] | None = None) -> OAuthClientOut:
        """Create an API client BOUND TO THIS ORGANIZATION. Returns a one-time secret.

        THIS IS NOT `register_oauth_client`, and the difference decides whether the
        credential works:

          create_oauth_client     authenticated, and BOUND TO YOUR ORGANIZATION. The
          (this tool)             resulting client can read your courses and learners,
                                  within the scopes you give it.

          register_oauth_client   unauthenticated RFC 7591 dynamic registration. Skilljar
                                  binds NO organization to it. The client authenticates
                                  fine and then reads nothing, forever, with no error
                                  that says why.

        Use this one unless you specifically need dynamic registration.

        Scope it with EITHER `scope_codenames` (exact, from `list_oauth_scopes`) OR
        `scope_preset` (a named bundle). Not both — they are two ways of saying the same
        thing and sending both is ambiguous. Give the smallest set that works: scopes are
        the only control that survives a leaked secret.

        `ip_allowlist` restricts where the client may be used from. Empty means anywhere.

        THE RETURNED SECRET IS SHOWN ONCE. There is no endpoint that reads it back; if it
        is lost the client must be rotated or replaced.

        Requires the `clients:write` OAuth scope, and the `admin` capability profile.
        """
        if not name:
            raise ValueError("name is required")
        if scope_codenames is not None and scope_preset is not None:
            raise ValueError(
                "send scope_codenames OR scope_preset, not both - they are two ways to "
                "say the same thing, and which one wins is not defined. Use "
                "list_oauth_scopes to see the codenames and the presets.")
        if scope_codenames is None and scope_preset is None:
            raise ValueError(
                "give the client some scopes: scope_codenames (from list_oauth_scopes) "
                "or scope_preset. A client with none can authenticate and do nothing, "
                "which looks like a broken credential rather than an empty one.")
        row = get_client().create_oauth_client(
            name=name, description=description, scope_codenames=scope_codenames,
            scope_preset=scope_preset, ip_allowlist=ip_allowlist)["data"]
        return _flatten(row, with_secret=True)

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_oauth_client(id: str, name: str | None = None,
                            description: str | None = None,
                            scope_codenames: list[str] | None = None,
                            scope_preset: str | None = None,
                            ip_allowlist: list[str] | None = None) -> OAuthClientOut:
        """Change an API client's name, description, scopes or IP allowlist.

        `id` is the client's record id from `list_oauth_clients`.

        `scope_codenames` REPLACES the client's scopes rather than adding to them. To
        add one, read the current set with `get_oauth_client` and send all of them plus
        the new one — sending only the new one removes every other.

        NARROWING SCOPES TAKES EFFECT ON THE NEXT TOKEN, not immediately. A token already
        issued keeps the scopes it was minted with until it expires. If you are narrowing
        a client because its secret leaked, narrowing alone is not enough: also
        rotate the secret, and revoke any refresh token you know of.

        Send `scope_codenames` OR `scope_preset`, not both.

        The client's secret is NOT changed here and is not returned.

        Requires the `clients:write` OAuth scope, and the `admin` capability profile.
        """
        if not id:
            raise ValueError("id is required")
        if scope_codenames is not None and scope_preset is not None:
            raise ValueError("send scope_codenames OR scope_preset, not both")
        changes = {k: v for k, v in (
            ("name", name), ("description", description),
            ("scope_codenames", scope_codenames), ("scope_preset", scope_preset),
            ("ip_allowlist", ip_allowlist)) if v is not None}
        if not changes:
            raise ValueError(
                f"nothing to change. Send at least one of "
                f"{', '.join(sorted(_UPDATE_FIELDS))}.")
        return _flatten(get_client().update_oauth_client(
            client_id=id, changes=changes)["data"])

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def rotate_oauth_client_secret(id: str) -> OAuthClientOut:
        """Issue a NEW secret for an API client. THE OLD ONE STOPS WORKING IMMEDIATELY.

        `id` is the client's record id from `list_oauth_clients`.

        This is the remediation tool for a leaked secret, and it is disruptive on
        purpose: the moment it returns, EVERY SERVICE STILL USING THE OLD SECRET IS
        BROKEN and will fail to obtain a token. Know what uses the client before rotating
        it, and have somewhere to put the new secret first.

        The new secret is SHOWN ONCE in this response and cannot be retrieved again. If
        you lose it you must rotate again, breaking everything a second time.

        Rotating does not revoke tokens already issued — those live until they expire.
        Use `revoke_refresh_token` for any refresh token you know of.

        Requires the `clients:write` OAuth scope, and the `admin` capability profile.
        """
        if not id:
            raise ValueError("id is required")
        return _flatten(get_client().rotate_oauth_client_secret(client_id=id)["data"],
                        with_secret=True)

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def deactivate_oauth_client(id: str) -> OAuthClientOut:
        """Turn an API client off. It can no longer obtain a token.

        `id` is the client's record id from `list_oauth_clients`.

        THIS IS A DEACTIVATION, NOT A DELETION. Skilljar's endpoint is a DELETE verb but
        its own summary calls it "Deactivate client": the record survives, keeps its
        name, scopes and history, and continues to appear in `list_oauth_clients` with
        `is_active` false. Do not report it as deleted.

        Anything using this client stops working at its next token request. A token
        already issued lives until it expires, so deactivating is not instant lockout —
        pair it with `revoke_refresh_token` if you need the access gone now.

        Requires the `clients:write` OAuth scope, and the `admin` capability profile.
        """
        if not id:
            raise ValueError("id is required")
        return _flatten(get_client().deactivate_oauth_client(client_id=id)["data"])

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def revoke_refresh_token(token: str,
                             token_type_hint: str | None = "refresh_token"  # nosec B107 # RFC 7009 hint value, not a password
                             ) -> RevocationOut:
        """Revoke a refresh token. SUCCESS HERE IS NOT EVIDENCE THAT ANYTHING HAPPENED.

        `token` is the refresh token itself, not a client id and not an access token.

        THE ENDPOINT ANSWERS SUCCESS WHETHER OR NOT THE TOKEN EXISTED. RFC 7009 §2.2
        specifies that deliberately, so the endpoint cannot be used to discover whether a
        token is valid. A typo, an already-revoked token and a real revocation are
        indistinguishable in the response. Report that this was REQUESTED, never that it
        was confirmed.

        This is also the one call in this server that sends no credentials at all — the
        token is the authorization. Do not paste one into a transcript on the way here.

        Revoking a refresh token does not kill access tokens already issued from it;
        those live until they expire, which for this API is fifteen minutes.

        Requires the `admin` capability profile. No OAuth scope, because no token of ours
        is sent.
        """
        if not token:
            raise ValueError("token is required - the refresh token to revoke")
        get_client().revoke_refresh_token(token=token, token_type_hint=token_type_hint)
        return {"requested": True,
                "note": "Revocation was REQUESTED. This endpoint answers success whether "
                        "or not the token existed (RFC 7009), so this is not "
                        "confirmation that a token was revoked."}
