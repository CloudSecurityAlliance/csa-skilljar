"""Webhooks and event payloads.

Two unrelated jobs, and one of them is a redaction problem.

**Webhook configuration carries live secrets.** Verified against the live API on
2026-08-28, `/v1/webhooks` returns them in three separate places:

  * `additional_headers` values — a 32-character `X-Skilljar-Secret` came back in
    PLAINTEXT
  * `target_url` query strings — two of three targets carry an `auth` parameter
  * `basic_auth_password` — the field exists on every row

So the raw response is a set of credentials for whatever those webhooks authenticate to.
These tools return the SHAPE of a webhook — where it points, what it fires on, whether
it is on — and never the values. Header names yes, header values no. Host and path yes,
query string no.

The second job is compression. v1 exposes TEN `sample-*` endpoints, one per event type,
each returning an example payload. That is ten tools' worth of surface for one question:
"what does a FOO event look like?" `preview_event_payload` takes the event type and
picks the endpoint, so the tool surface matches the question rather than the API.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import CommerceListOut
from ._base import READ, translate_errors

# event_type as it appears on a webhook -> the sample-* slug. Mechanical, but written out
# so an unknown type is a clear error rather than a 404 from a guessed URL.
EVENT_TYPES = {
    "COURSE_COMPLETION": "course-completion",
    "COURSE_ENROLLMENT": "course-enrollment",
    "DASHBOARD_TASK_CREATED": "dashboard-task-created",
    "DOMAIN_ENROLLMENT": "domain-enrollment",
    "LESSON_COMPLETION": "lesson-completion",
    "PATH_COMPLETION": "path-completion",
    "PATH_ENROLLMENT": "path-enrollment",
    "PURCHASE_FULFILLMENT": "purchase-fulfillment",
    "QUIZ_COMPLETION": "quiz-completion",
    "VILT_REGISTRATION": "vilt-registration",
}

_REDACTED = "<withheld by csa-skilljar>"
_WITHHELD_NOTE = (
    "Webhook secrets are WITHHELD. Skilljar returns a shared-secret header value, any "
    "token in the target URL's query string, and a Basic-auth password in plain text; "
    "none of them are returned here. Header NAMES and the URL's host and path are, "
    "because those answer where an event goes without handing over the credential.")


def _safe_url(url: str | None) -> dict[str, Any]:
    """Host and path, never the query string - two of three live targets carry a token
    in theirs."""
    if not url:
        return {}
    parts = urlsplit(url)
    out: dict[str, Any] = {
        "target_url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))}
    if parts.query:
        # Say a query string existed, and name its parameters, without the values. "The
        # URL has an `auth` parameter" is useful; its value is the credential.
        out["target_url_query_parameters_withheld"] = sorted(
            {p.split("=", 1)[0] for p in parts.query.split("&") if p})
    return out


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in ("event_type", "active", "deactivate_reason"):
        if key in row:
            out[key] = row[key]
    out.update(_safe_url(row.get("target_url")))
    headers = row.get("additional_headers")
    if isinstance(headers, dict):
        # NAMES only. The value of X-Skilljar-Secret is what the receiver checks.
        out["additional_header_names"] = sorted(headers)
    if row.get("basic_auth_username"):
        out["basic_auth_username"] = row["basic_auth_username"]
    if row.get("basic_auth_password"):
        out["basic_auth_password"] = _REDACTED
    return out


def register_event_tools(app: MCPServer,
                         get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_webhooks(page: int | None = None,
                      page_size: int | None = None) -> CommerceListOut:
        """List webhook subscriptions - where Skilljar sends events, and on what.

        SECRETS ARE WITHHELD. Skilljar returns a shared-secret header value, any token in
        the target URL's query string, and a Basic-auth password in plain text. None of
        those are returned here. You get the header NAMES, and the URL's host and path,
        which answer where an event goes without handing over the credential.

        `event_type` is what fires it - `preview_event_payload` shows the shape of that
        event's body. `active` false with a `deactivate_reason` usually means Skilljar
        turned it off after repeated delivery failures, which is worth reporting: a
        webhook can be configured correctly and still be dead.

        To see a secret, read it in the Skilljar Dashboard. It is deliberately not
        available through this server.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        size = page_size or 25
        if not 1 <= size <= 250:
            raise ValueError("page_size must be between 1 and 250")
        got = get_client().list_webhooks(page=page, page_size=size)
        out: CommerceListOut = {"rows": [_flatten(r) for r in got["rows"]],
                                "note": _WITHHELD_NOTE}
        if got.get("total") is not None:
            out["total"] = got["total"]
        out["page"] = page or 1
        out["has_more"] = bool(got.get("has_more"))
        if got.get("next_page") is not None:
            out["next_page"] = got["next_page"]
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_webhook(id: str) -> dict[str, Any]:
        """Fetch one webhook subscription. SECRETS ARE WITHHELD.

        Same redaction as `list_webhooks`: header names but not values, the target URL's
        host and path but not its query string, and never the Basic-auth password.

        `deactivate_reason` is the useful field when something stopped working - a
        webhook Skilljar disabled after failed deliveries looks identical to a healthy
        one apart from `active` and that reason.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not id:
            raise ValueError("id is required - the webhook id, from list_webhooks")
        row = get_client().get_webhook(webhook_id=id)["rows"][0]
        out = _flatten(row)
        out["note"] = _WITHHELD_NOTE
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def preview_event_payload(event_type: str) -> dict[str, Any]:
        """Show an EXAMPLE payload for one webhook event type.

        `event_type` is the value a webhook carries - `COURSE_COMPLETION`,
        `PURCHASE_FULFILLMENT` and so on. `list_webhooks` shows which are subscribed;
        this works for all ten whether or not anything is listening.

        Use it to answer "what fields will I get" before writing a receiver, and to check
        whether an event carries the data a workflow needs.

        THE PAYLOAD IS AN EXAMPLE, NOT A REAL EVENT. Skilljar returns sample data; the
        ids and names in it refer to nothing. Do not report them as real records, and do
        not look up the ids.

        One tool rather than ten: v1 has a separate endpoint per event type, which is ten
        tools' worth of surface for a single question.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not event_type:
            raise ValueError(
                f"event_type is required. One of: {', '.join(sorted(EVENT_TYPES))}")
        key = event_type.strip().upper().replace("-", "_")
        if key not in EVENT_TYPES:
            raise ValueError(
                f"unknown event_type {event_type!r}. Skilljar defines exactly these: "
                f"{', '.join(sorted(EVENT_TYPES))}.")
        got = get_client().get_sample_event_payload(slug=EVENT_TYPES[key])
        return {"event_type": key,
                "example_payload": got["rows"][0] if got["rows"] else None,
                "note": "An EXAMPLE payload. The ids and names in it are sample data and "
                        "refer to no real record - do not look them up or report them "
                        "as findings."}
