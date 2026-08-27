"""The seam. `Backend` is the protocol; `PolicyBackend` wraps it; `V2Backend` is real.

Every method takes keyword-only arguments so `PolicyBackend` can wrap uniformly, and
returns the raw v2 JSON:API envelope - shaping belongs to the delivery layer, not here.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

from . import exceptions as exc
from .auth import V2Credentials
from .scopes import is_known_operation, scopes_for

Envelope = dict[str, Any]


def parse_batch(envelope: Envelope) -> dict[str, Any]:
    """Split a 207 batch envelope into succeeded and failed items.

    v2 collection writes return per-item results rather than one status for the whole
    request. Preserving that split is the point: a caller told only "the batch failed"
    cannot tell which forty-nine rows landed.

    The `succeeded + failed == total` invariant is CHECKED, not trusted. Skilljar
    enforces it server-side, so a mismatch means we are misreading the envelope - and
    reporting a confidently wrong count is worse than raising.
    """
    summary = envelope.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("batch response carried no summary; this is not a 207 envelope")
    total = int(summary.get("total", 0))
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in envelope.get("data", []):
        if item.get("status") == "error":
            failed.append({
                "code": item.get("code", "unknown"),
                "detail": item.get("detail", ""),
                "pointer": (item.get("source") or {}).get("pointer", ""),
            })
        else:
            succeeded.append(item)
    if len(succeeded) + len(failed) != total:
        raise ValueError(
            f"batch summary disagrees with its own data: summary total={total} but "
            f"{len(succeeded)} succeeded + {len(failed)} failed were present")
    return {"succeeded": succeeded, "failed": failed, "total": total}


@runtime_checkable
class Backend(Protocol):
    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope: ...


class FakeBackend:
    """In-memory double. Powers the entire offline suite - no network, no credentials.

    Deliberately implements the *shape* of v2's cursor pagination, including the
    `has_more` / `next_cursor` pair, because code that only ever sees a single page
    is code that has never exercised paging.
    """

    def __init__(self, courses: list[dict[str, Any]] | None = None) -> None:
        self._courses = list(courses or [])

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        rows = self._courses
        if title is not None:
            needle = title.lower()
            rows = [c for c in rows if needle in c.get("attributes", {}).get("title", "").lower()]
        start = int(cursor) if cursor else 0
        size = page_size or 25
        page = rows[start:start + size]
        nxt = start + size
        more = nxt < len(rows)
        return {"data": page, "meta": {"page_size": size},
                "links": {"self": "/v2/courses/", "next": None, "prev": None},
                "has_more": more, "next_cursor": str(nxt) if more else None}


class V2Backend:
    """The v2 API. JSON:API envelopes, cursor pagination, per-operation OAuth scopes.

    The scope pre-check runs BEFORE the request: v2 declares `x-required-scope` on every
    operation and the granted scopes are readable from the token, so an impossible call
    is refused locally with an exact remedy and zero network traffic.
    """

    def __init__(self, credentials: V2Credentials, *,
                 base_url: str = "https://api.skilljar.com",
                 http: httpx.Client | None = None) -> None:
        self._creds = credentials; self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Envelope:
        # ZD-2: an unknown path must not look like "declared, needs no scope". Without
        # this, a typo silently disables the scope pre-check - a control failing open
        # and saying nothing.
        if not is_known_operation("GET", path):
            raise exc.ApiError(
                f"GET {path} is not a known v2 operation. This is a bug in csa-skilljar: "
                f"the path is absent from the generated scope table. Regenerate with "
                f"scripts/gen_scopes.py if specs/ was refreshed.")
        needed = scopes_for("GET", path)
        if needed:
            granted = set(self._creds.granted_scopes())
            if not granted & set(needed):        # any-of semantics
                self._creds.require_scope(needed[0])
        try:
            r = self._http.get(
                f"{self._base}{path}",
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers={"Authorization": f"Bearer {self._creds.token()}",
                         "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach Skilljar: {e}") from e
        if r.status_code == 404:
            raise exc.NotFoundError(f"not found: {path}")
        if r.status_code in (401, 403):
            raise exc.CredentialsRejected(
                "Skilljar rejected the v2 access token. The client may have been deleted or "
                "its credentials rotated. Re-issue the client and restart the server.")
        if r.status_code >= 400:
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {path}", status=r.status_code)
        # ZD-2: "responses that technically succeed but look wrong - error on all of it."
        try:
            body = r.json()
        except ValueError as e:
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {path} with a body that is "
                f"not JSON", status=r.status_code) from e
        if not isinstance(body, dict):
            raise exc.ApiError(
                f"Skilljar returned HTTP {r.status_code} for {path} with JSON that is not "
                f"an object (got {type(body).__name__})", status=r.status_code)
        result: Envelope = body
        return result

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        return self._get("/v2/courses/", {
            "filter[title]": title,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})
