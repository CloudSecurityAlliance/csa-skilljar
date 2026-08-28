"""The v1 API — the second backend, and a different API in almost every respect.

v1 is not v2 with different paths. Everything about the transport differs, and the
differences are the reason this is a separate module rather than a branch inside
`V2Backend`:

              v1                                   v2
  auth        HTTP Basic, key as username          OAuth bearer, client_credentials
  envelope    `{count,next,previous,results}`      JSON:API `{data, meta, links}`
              OR a bare JSON array                 (uniform)
  paging      `?page=N`, with a TOTAL COUNT        opaque cursor, no total
  errors      `{"detail": "..."}`                  `{"errors":[{...}]}`

ADR-002 governs when this is used at all: **v2 owns every capability v2 has; v1 is used
only for capabilities v2 lacks.** There is no fallback in either direction. A capability
served by both would give callers two different data shapes for the same question
depending on which backend answered, which is the failure this rule exists to prevent.

The two envelope shapes are the trap. `GET /v1/users` returns the DRF envelope;
`GET /v1/users/{id}/published-courses` returns a BARE ARRAY. Verified against the live
API on 2026-08-28. A reader that assumes one shape silently returns nothing for the
other - no error, just an empty list.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from . import exceptions as exc

Envelope = dict[str, Any]

DEFAULT_BASE = "https://api.skilljar.com"
_TIMEOUT = 30.0


class V1Credentials:
    """An organisation API key, used as HTTP Basic with an EMPTY password.

    Skilljar's own scheme: the key is the username and the password is blank. Sending it
    as a bearer token, or as the password, returns 401 - which looks exactly like a bad
    key and sends people to reissue a credential that was fine.

    Unlike v2 there is no token, no expiry and no scopes: the key IS the authorization,
    it is organisation-wide, and Skilljar offers no way to narrow it. That asymmetry is
    recorded as an accepted risk in SECURITY-RESOURCES.md.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise exc.CredentialsMissing("a v1 API key is required")
        self._key = api_key

    def header(self) -> str:
        # `key:` - the trailing colon is the empty password, and it is load-bearing.
        token = base64.b64encode(f"{self._key}:".encode()).decode()
        return f"Basic {token}"

    def __repr__(self) -> str:
        # Hand-written: embedders log clients, and a default repr here is a key leak.
        return "V1Credentials(api_key=<redacted>)"


def parse_page(payload: Any) -> dict[str, Any]:
    """Normalise either v1 envelope into one shape: rows, total, and whether more exist.

    v1 answers in two shapes and the caller cannot tell which is coming:

      {"count": 42, "next": "...", "previous": null, "results": [...]}   paginated
      [ {...}, {...} ]                                                   bare array

    Returning a common shape here rather than at each call site is what stops half the
    tools quietly returning nothing. `total` is None for a bare array, because the
    endpoint genuinely does not say - which is different from a total of zero.
    """
    if isinstance(payload, list):
        return {"rows": payload, "total": None, "has_more": False, "next_page": None}
    if not isinstance(payload, dict):
        raise exc.ApiError(
            f"v1 returned {type(payload).__name__}, which is neither a paginated "
            f"envelope nor a list of rows")
    if "results" not in payload:
        # A single object, e.g. GET /v1/users/{id}. One row, not zero.
        return {"rows": [payload], "total": 1, "has_more": False, "next_page": None}
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise exc.ApiError("v1 envelope has `results` that is not a list")
    nxt = payload.get("next")
    return {"rows": rows,
            # v1 gives a TOTAL, which v2 never does. Worth surfacing: it is the only way
            # to say "3 of 4,278" rather than "3, and maybe more".
            "total": payload.get("count"),
            "has_more": bool(nxt),
            "next_page": _page_of(nxt)}


def _page_of(url: str | None) -> int | None:
    """The `page` number out of a v1 `next` URL.

    v1 pages by NUMBER, not by an opaque cursor. Handing the caller the raw URL would
    leak the base host into tool output and make the next call untestable, so the number
    is extracted and the caller passes `page=N` back.
    """
    if not url:
        return None
    from urllib.parse import parse_qs, urlparse
    values = parse_qs(urlparse(url).query).get("page")
    if not values:
        return None
    try:
        return int(values[0])
    except (TypeError, ValueError):
        # A `next` we cannot parse is not a crash - but it must not silently become
        # "there is no next page", which would truncate every listing at page one.
        raise exc.ApiError(
            f"v1 gave a next-page link this client cannot read: {values[0]!r}") from None


class V1Backend:
    """The v1 API. Reads only, for now - see WAITING-FOR-003."""

    def __init__(self, creds: V1Credentials, *, base_url: str = DEFAULT_BASE,
                 http: Any | None = None) -> None:
        self._creds = creds
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=_TIMEOUT)

    def __repr__(self) -> str:
        return f"V1Backend(base_url={self._base!r})"

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = self._http.get(
                f"{self._base}{path}",
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers={"Authorization": self._creds.header(),
                         "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach Skilljar v1: {e}") from e
        return self._receive(r, path)

    def _receive(self, r: Any, path: str) -> Any:
        if r.status_code == 404:
            # v1 answers 404 both for "no such row" and "no such endpoint", and the
            # published v1 spec documents endpoints this deployment does not serve -
            # per-lesson progress among them. Say so, because "not found" alone sends
            # someone hunting for an id that was never the problem.
            raise exc.NotFoundError(
                f"v1 returned 404 for {path}. Either the record does not exist, or this "
                f"endpoint is not served - Skilljar's published v1 document describes "
                f"some that are not.")
        if r.status_code in (401, 403):
            raise exc.CredentialsRejected(
                "Skilljar rejected the v1 API key. Note v1 uses HTTP Basic with the key "
                "as the USERNAME and an empty password; a key sent as a bearer token "
                "fails exactly this way. Check the key in your MCP client configuration.")
        if r.status_code >= 400:
            raise exc.ApiError(f"Skilljar v1 returned HTTP {r.status_code} for {path}",
                               status=r.status_code)
        try:
            return r.json()
        except ValueError as e:
            raise exc.ApiError(
                f"v1 returned HTTP {r.status_code} for {path} with a body that is not "
                f"JSON") from e

    # --- learner progress (the first v1-only capability) --------------------------------

    def list_learner_progress(self, *, user_id: str,
                              page: int | None = None) -> Envelope:
        """Every course this learner is enrolled in, with per-course progress.

        Returns a BARE ARRAY upstream, not the paginated envelope - `parse_page` absorbs
        the difference.
        """
        return parse_page(self._get(f"/v1/users/{user_id}/published-courses",
                                    {"page": page}))

    def get_learner_progress(self, *, user_id: str,
                             published_course_id: str) -> Envelope:
        """One enrolment, selected from the list rather than fetched by id.

        NOT `/v1/users/{uid}/published-courses/{pcid}`, which looks like the obvious
        endpoint and is wrong. It resolves by the UNDERLYING COURSE, not by the
        publication, so when a course is published to more than one domain it returns a
        DIFFERENT publication than the one asked for - with a 200 and no indication
        anything was substituted.

        Observed 2026-08-28 against the live API. A learner with 54 enrolments had one
        course published to two domains:

            asked 17reo6su7ohtp (cloudsecurityalliance.skilljar.com)
            got   2jpjwm93w06xq (training.cloudsecurityalliance.org)

        The other 53 matched, which is what makes it dangerous: it is right until the
        exact case where a domain matters, and a wrong 200 is worse than a 404.

        The list endpoint returns every enrolment in one unpaginated array, so selecting
        locally costs the same single request and cannot return the wrong publication.
        """
        listing = self.list_learner_progress(user_id=user_id)
        for row in listing["rows"]:
            if row.get("published_course_id") == published_course_id:
                return {"rows": [row], "total": 1, "has_more": False, "next_page": None}
        raise exc.NotFoundError(
            f"learner {user_id} has no enrolment in published course "
            f"{published_course_id}. They have {len(listing['rows'])} enrolments; "
            f"list_learner_progress shows them.")

    def find_learner(self, *, email: str) -> Envelope:
        """Resolve an email to a learner id, using the DRF-enveloped `/v1/users`.

        Kept because it is the other envelope shape, and because a caller holding only an
        email would otherwise have to reach into v2 to start a v1 call.
        """
        return parse_page(self._get("/v1/users", {"email": email}))
