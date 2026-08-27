"""Web packages (SCORM and similar archives), and OAuth client registration.

Two unrelated families, kept together because they are what remains of the official
server's surface and neither justifies a module.

Web packages are the only ASYNCHRONOUS family in this API. Creating one queues an
outbound fetch: the response says PROCESSING, and whether the archive was any good is
not known until a worker has finished with it. A tool description that omits this leads
a model to report success for something that later failed.

`register_oauth_client` is the only UNAUTHENTICATED call in the whole server, and the
only one that returns a credential.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...backend import parse_batch
from ...client import SkilljarClient
from .._schemas import (
    BatchResultOut,
    RegisteredClientOut,
    WebPackageListOut,
    WebPackageOut,
)
from ._base import DESTRUCTIVE, READ, WRITE, translate_errors

_MAX_TITLE = 500
# Upstream accepts these on update and SILENTLY IGNORES them - unusual for this API,
# which mostly forbids extras outright. ADR-008: refuse, so the caller is not misled.
_IGNORED_ON_UPDATE = frozenset({"type", "state", "base_path", "display_name"})
_AUTH_METHODS = ("client_secret_post", "client_secret_basic", "none")

_ASYNC_NOTE = ("Creating a package only QUEUES it. Rows come back in state PROCESSING; "
               "poll get_web_package until state is READY or ERROR. A bad archive shows "
               "up as state ERROR later, never as a failure on the create call.")
_LIST_NOTE = ("This list is not paginated - every live package is here. Deleted "
              "packages are not shown.")
_SHOWN_ONCE_WARNING = (
    "If a client_secret is present it is shown ONCE and cannot be retrieved again. "
    "Store it somewhere durable before doing anything else. Do not paste it into a "
    "chat transcript, a ticket, or a file that will be committed.")


def _batch_out(envelope: dict[str, Any], note: str) -> BatchResultOut:
    parsed = parse_batch(envelope)
    return {"total": parsed["total"], "succeeded": len(parsed["succeeded"]),
            "failed": parsed["failed"],
            "ids": [s.get("id", "") for s in parsed["succeeded"]], "note": note}


def _flatten(row: dict[str, Any]) -> WebPackageOut:
    attrs = row.get("attributes", {})
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in ("title", "display_name", "state", "base_path", "created_at",
                "modified_at"):
        if key in attrs:
            out[key] = attrs[key]
    # `type` is the package format (SCORM and so on). It collides with JSON:API's own
    # `type`, so it is renamed on the way out rather than shadowing the resource type.
    if "type" in attrs:
        out["package_type"] = attrs["type"]
    return cast(WebPackageOut, out)


def _check_title(attrs: dict[str, Any], where: str) -> None:
    title = attrs.get("title")
    if not title or not isinstance(title, str):
        raise ValueError(f"{where} needs a title")
    if not 1 <= len(title) <= _MAX_TITLE:
        raise ValueError(f"{where} title must be 1 to {_MAX_TITLE} characters")


def register_web_package_tools(app: MCPServer,
                               get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_web_packages() -> WebPackageListOut:
        """List the organization's live web packages - SCORM and similar archives.

        A web package is a self-contained bundle of hosted content that a lesson can
        point at. This returns EVERY live one in a single response: it is not paginated
        and takes no arguments, because Skilljar's endpoint offers neither.

        Deleted packages are not listed. `state` is PROCESSING, READY or ERROR - only
        READY packages are usable by a lesson.

        Requires the `web-packages:read` OAuth scope.
        """
        envelope = get_client().list_web_packages()
        return {"web_packages": [_flatten(r) for r in envelope.get("data", [])],
                "note": _LIST_NOTE}

    @app.tool(annotations=READ)
    @translate_errors
    def get_web_package(id: str) -> WebPackageOut:
        """Fetch one web package, and check whether it finished ingesting.

        `id` is the obfuscated package id. THIS IS THE POLLING TOOL: after
        `create_web_packages`, call this until `state` stops being PROCESSING.

          PROCESSING   Skilljar is still fetching and re-hosting the archive
          READY        usable by a lesson
          ERROR        the archive was rejected - the create call did NOT report this

        `display_name` is derived, not the title you set. Until the package reaches
        READY it is the state plus the filename, so a title change looks as though it
        did nothing. Compare `title` to know what was actually stored.

        Requires the `web-packages:read` OAuth scope.
        """
        return _flatten(get_client().get_web_package(web_package_id=id)["data"])

    @app.tool(annotations=WRITE)
    @translate_errors
    def create_web_packages(web_packages: list[dict[str, Any]]) -> BatchResultOut:
        """Upload web packages from URLs. ASYNCHRONOUS - this only starts the job.

        `web_packages` is the batch: each item needs `content_url` (an https:// URL of
        the archive) and a `title` of 1 to 500 characters.

        SUCCESS HERE DOES NOT MEAN THE PACKAGE WORKS. Skilljar fetches and re-hosts the
        archive in a background worker. Rows come back in state PROCESSING, and a
        malformed or unreachable archive surfaces later as state ERROR on the package -
        never as a failure on this call. Poll `get_web_package` until `state` is READY
        or ERROR before telling anyone the upload worked.

        The URL is only checked for syntax here. Whether it resolves, and whether what
        it serves is a valid archive, is decided at fetch time.

        THERE IS NO DEDUPLICATION. Sending the same `content_url` twice creates two
        separate packages, because that is a legitimate thing to want. Every other
        create tool in this server dedups; this one does not.

        Each accepted item queues a real outbound download, so one request becomes real
        egress. This endpoint is rate limited more tightly than an ordinary batch write.
        Submit in small batches.

        Requires the `web-packages:write` OAuth scope.
        """
        if not web_packages:
            raise ValueError("web_packages must contain at least one item")
        for i, attrs in enumerate(web_packages):
            where = f"web_packages[{i}]"
            if not isinstance(attrs, dict):
                raise ValueError(f"{where} must be an object")
            unknown = sorted(set(attrs) - {"content_url", "title"})
            if unknown:
                raise ValueError(f"{where} has unknown attribute(s) "
                                 f"{', '.join(unknown)}. Allowed: content_url, title")
            url = attrs.get("content_url")
            if not url or not isinstance(url, str):
                raise ValueError(f"{where} needs a content_url")
            if not url.startswith("https://"):
                raise ValueError(f"{where} content_url must be an https:// URL, "
                                 f"got {url!r}")
            _check_title(attrs, where)
        return _batch_out(get_client().create_web_packages(items=web_packages),
                          _ASYNC_NOTE)

    @app.tool(annotations=WRITE)
    @translate_errors
    def update_web_packages(web_packages: list[dict[str, Any]]) -> BatchResultOut:
        """Rename web packages. This is a BATCH operation.

        `web_packages` is the batch, and each item is `{id, title}`. `title` IS THE
        ONLY WRITABLE FIELD.

        `type`, `state`, `base_path` and `display_name` are owned or derived by
        Skilljar. It ACCEPTS them here and silently ignores them - which is unusual for
        this API, and is why this tool refuses them instead of letting you believe a
        change happened. To replace a package's content, create a new package and
        repoint the lesson.

        A RENAME MAY LOOK LIKE IT DID NOTHING. `display_name` only starts tracking
        `title` once the package reaches READY; while it is PROCESSING or ERROR the
        display name stays as the state plus filename. Read `title` rather than
        `display_name` to confirm the change landed.

        Requires the `web-packages:write` OAuth scope.
        """
        if not web_packages:
            raise ValueError("web_packages must contain at least one item")
        for i, attrs in enumerate(web_packages):
            where = f"web_packages[{i}]"
            if not isinstance(attrs, dict):
                raise ValueError(f"{where} must be an object")
            if not attrs.get("id"):
                raise ValueError(f"{where} needs an `id`")
            blocked = sorted(set(attrs) & _IGNORED_ON_UPDATE)
            if blocked:
                raise ValueError(
                    f"{where} tries to set {', '.join(blocked)}, which Skilljar owns. "
                    f"It accepts these and silently ignores them, so they are refused "
                    f"here rather than appearing to work. Only `title` is writable.")
            unknown = sorted(set(attrs) - {"id", "title"})
            if unknown:
                raise ValueError(f"{where} has unknown attribute(s) "
                                 f"{', '.join(unknown)}. Allowed: id, title")
            _check_title(attrs, where)
        return _batch_out(get_client().update_web_packages(items=web_packages),
                          "Read `title` to confirm a rename - `display_name` lags "
                          "until the package is READY.")

    @app.tool(annotations=DESTRUCTIVE)
    @translate_errors
    def delete_web_package(id: str) -> WebPackageOut:
        """Delete one web package. Soft, and REFUSED while a live lesson uses it.

        `id` is the obfuscated package id. This takes one id, not a batch, because the
        conflict case below has no sensible place in a per-row batch result.

        If a lesson in a LIVE published course still points at this package, the call is
        REFUSED rather than partially applied - deleting it would leave that lesson with
        no content for learners who are looking at it right now. Unpublish the course or
        repoint the lesson first.

        The delete is soft: the package stops being listed, and existing references in
        unpublished courses are not rewritten.

        Requires the `web-packages:write` OAuth scope.
        """
        return _flatten(get_client().delete_web_package(web_package_id=id)["data"])

    @app.tool(annotations=WRITE)
    @translate_errors
    def register_oauth_client(client_name: str,
                              redirect_uris: list[str] | None = None,
                              grant_types: list[str] | None = None,
                              scope: str | None = None,
                              token_endpoint_auth_method: str = "client_secret_post",  # nosec B107 # RFC 7591 method name
                              resource: str = "") -> RegisteredClientOut:
        """Create a new OAuth2 client identity. THIS MINTS A CREDENTIAL.

        RFC 7591 Dynamic Client Registration. It is the only UNAUTHENTICATED call in
        this server: it does not use, and does not send, your Skilljar credentials.

        `client_name` is required, up to 255 characters. `redirect_uris`,
        `grant_types`, `scope` and `resource` are optional.

        `token_endpoint_auth_method` decides whether a secret is issued:
          `client_secret_post` (default) or `client_secret_basic` - a confidential
                               client, and a `client_secret` IS RETURNED
          `none`               a public/PKCE client, and NO secret is returned

        A RETURNED client_secret IS SHOWN ONCE AND CANNOT BE RETRIEVED AGAIN. There is
        no endpoint to read it back. If it is lost the client must be registered again.
        Hand it to a human to store; do not leave it sitting in a transcript.

        NO ORGANIZATION IS BOUND AT REGISTRATION. Skilljar does not associate a
        dynamically registered client with an organization or audit the registration, so
        a client made here is NOT a substitute for an organization-scoped credential
        issued through Skilljar. It will not read your courses.

        This tool is off unless the `admin` capability profile is enabled, even though
        Skilljar's own server ships it enabled.

        No OAuth scope is required, because no token is sent.
        """
        if not client_name:
            raise ValueError("client_name is required")
        if len(client_name) > 255:
            raise ValueError("client_name must be at most 255 characters")
        if token_endpoint_auth_method not in _AUTH_METHODS:
            raise ValueError(
                f"token_endpoint_auth_method must be one of "
                f"{', '.join(_AUTH_METHODS)}; got {token_endpoint_auth_method!r}")
        payload = get_client().register_oauth_client(
            client_name=client_name, redirect_uris=redirect_uris,
            grant_types=grant_types, scope=scope,
            token_endpoint_auth_method=token_endpoint_auth_method,
            resource=resource)["data"]
        out: dict[str, Any] = {"warning": _SHOWN_ONCE_WARNING}
        for key in ("client_id", "client_secret", "client_name", "redirect_uris",
                    "grant_types", "token_endpoint_auth_method", "scope"):
            if key in payload:
                out[key] = payload[key]
        return cast(RegisteredClientOut, out)
