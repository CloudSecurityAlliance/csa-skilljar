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

    def get_course(self, *, course_id: str) -> Envelope: ...

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope: ...

    def get_lesson(self, *, lesson_id: str) -> Envelope: ...


class FakeBackend:
    """In-memory double. Powers the entire offline suite - no network, no credentials.

    Deliberately implements the *shape* of v2's cursor pagination, including the
    `has_more` / `next_cursor` pair, because code that only ever sees a single page
    is code that has never exercised paging.
    """

    def __init__(self, courses: list[dict[str, Any]] | None = None,
                 lessons: list[dict[str, Any]] | None = None) -> None:
        self._courses = list(courses or [])
        self._lessons = list(lessons or [])

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        rows = self._courses
        if title is not None:
            needle = title.lower()
            rows = [c for c in rows if needle in c.get("attributes", {}).get("title", "").lower()]
        return self._page(rows, cursor, page_size, "/v2/courses/")

    def _page(self, rows: list[dict[str, Any]], cursor: str | None,
              page_size: int | None, self_link: str) -> Envelope:
        """v2's cursor pagination shape, shared by every listing.

        The cursor is an integer index here and an opaque token upstream - which is
        exactly why `tests/integration/` has to prove real pagination separately.
        """
        start = int(cursor) if cursor else 0
        size = page_size or 25
        page = rows[start:start + size]
        nxt = start + size
        more = nxt < len(rows)
        return {"data": page, "meta": {"page_size": size},
                "links": {"self": self_link, "next": None, "prev": None},
                "has_more": more, "next_cursor": str(nxt) if more else None}

    def get_course(self, *, course_id: str) -> Envelope:
        for row in self._courses:
            if row.get("id") == course_id:
                return {"data": row}
        raise exc.NotFoundError(f"no course with id {course_id}")

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        rows = self._lessons
        if course_id is not None:
            rows = [x for x in rows if x.get("attributes", {}).get("course_id") == course_id]
        if title is not None:
            # EXACT match, case-insensitive - unlike course titles, which match partially.
            rows = [x for x in rows
                    if x.get("attributes", {}).get("title", "").lower() == title.lower()]
        if lesson_type is not None:
            rows = [x for x in rows if x.get("attributes", {}).get("type") == lesson_type]
        if updated_since is not None:
            rows = [x for x in rows
                    if x.get("attributes", {}).get("modified_at", "") >= updated_since]
        return self._page(rows, cursor, page_size, "/v2/lessons/")

    def get_lesson(self, *, lesson_id: str) -> Envelope:
        for row in self._lessons:
            if row.get("id") == lesson_id:
                return {"data": row}
        raise exc.NotFoundError(f"no lesson with id {lesson_id}")


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

    def _get(self, path: str, params: dict[str, Any] | None = None,
             *, template: str | None = None) -> Envelope:
        """GET `path`, looking up the required scope under `template`.

        Scope lookup is by literal spec path, so an interpolated `/v2/courses/abc123`
        never matches `/v2/courses/{id}`. Callers with an id in the path pass the
        template separately rather than having the scope pre-check silently skipped.
        """
        spec_path = template or path
        # ZD-2: an unknown path must not look like "declared, needs no scope". Without
        # this, a typo silently disables the scope pre-check - a control failing open
        # and saying nothing.
        if not is_known_operation("GET", spec_path):
            raise exc.ApiError(
                f"GET {spec_path} is not a known v2 operation. This is a bug in "
                f"csa-skilljar: the path is absent from the generated scope table. "
                f"Regenerate with scripts/gen_scopes.py if specs/ was refreshed.")
        needed = scopes_for("GET", spec_path)
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

    def get_course(self, *, course_id: str) -> Envelope:
        return self._get(f"/v2/courses/{course_id}", template="/v2/courses/{id}")

    def list_lessons(self, *, course_id: str | None = None, title: str | None = None,
                     lesson_type: str | None = None, updated_since: str | None = None,
                     cursor: str | None = None, page_size: int | None = None) -> Envelope:
        return self._get("/v2/lessons/", {
            "filter[course_id]": course_id, "filter[title]": title,
            "filter[type]": lesson_type, "filter[updated_since]": updated_since,
            "page[cursor]": cursor,
            "page[size]": page_size if page_size is None else str(page_size)})

    def get_lesson(self, *, lesson_id: str) -> Envelope:
        return self._get(f"/v2/lessons/{lesson_id}", template="/v2/lessons/{id}")
