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

    # --- assets (v2 has no assets endpoint at all) --------------------------------------

    def list_assets(self, *, page: int | None = None) -> Envelope:
        """Every asset in the library. DRF-enveloped, with a total.

        Carries NO `download_url` - only the detail view does. That asymmetry is the
        reason `get_asset` exists, and a caller who lists and finds no URL would
        otherwise conclude there is none.
        """
        return parse_page(self._get("/v1/assets", {"page": page}))

    def get_asset(self, *, asset_id: str) -> Envelope:
        """One asset, including a `download_url` the listing does not carry.

        That URL is a PRESIGNED S3 link: it expires in about an hour, it is different on
        every fetch, and it works with no Skilljar credentials at all. Verified with a
        ranged GET carrying no authorization: 206, application/pdf.
        """
        return parse_page(self._get(f"/v1/assets/{asset_id}"))

    # --- commerce (v2 has no commerce surface at all) -----------------------------------

    def list_promo_codes(self, *, active: bool | None = None, code: str | None = None,
                         promo_code_pool_id: str | None = None,
                         page: int | None = None,
                         page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/promo-codes", {
            "active": None if active is None else str(active).lower(),
            "code": code, "promo_code_pool_id": promo_code_pool_id,
            "page": page, "page_size": page_size}))

    def list_promo_code_pools(self, *, name: str | None = None,
                              offer_id: str | None = None, page: int | None = None,
                              page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/promo-code-pools", {
            "name": name, "offer_id": offer_id,
            "page": page, "page_size": page_size}))

    def list_offers(self, *, page: int | None = None,
                    page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/offers",
                                    {"page": page, "page_size": page_size}))

    def list_training_credit_codes(self, *, tracking_identifier: str | None = None,
                                   training_credit_code: str | None = None,
                                   page: int | None = None,
                                   page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/training-credit-codes", {
            "tracking_identifier": tracking_identifier,
            "training_credit_code": training_credit_code,
            "page": page, "page_size": page_size}))

    def get_purchase(self, *, purchase_id: str) -> Envelope:
        """By id only. v1 offers NO purchase listing, so an id must come from elsewhere -
        a fulfillment webhook, or an order reference someone already has."""
        return parse_page(self._get(f"/v1/purchases/{purchase_id}"))

    # --- learning paths (v2 has no path or series surface at all) -----------------------

    def list_paths(self, *, page: int | None = None,
                   page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/paths",
                                    {"page": page, "page_size": page_size}))

    def get_path(self, *, path_id: str) -> Envelope:
        return parse_page(self._get(f"/v1/paths/{path_id}"))

    def list_path_items(self, *, path_id: str, page: int | None = None,
                        page_size: int | None = None) -> Envelope:
        return parse_page(self._get(f"/v1/paths/{path_id}/path-items",
                                    {"page": page, "page_size": page_size}))

    def list_published_paths(self, *, domain_name: str, page: int | None = None,
                             page_size: int | None = None) -> Envelope:
        return parse_page(self._get(f"/v1/domains/{domain_name}/published-paths",
                                    {"page": page, "page_size": page_size}))

    def list_course_series(self, *, domain_name: str, page: int | None = None,
                           page_size: int | None = None) -> Envelope:
        return parse_page(self._get(f"/v1/domains/{domain_name}/course-series",
                                    {"page": page, "page_size": page_size}))

    def list_learner_path_enrollments(self, *, user_id: str) -> Envelope:
        return parse_page(self._get(f"/v1/users/{user_id}/published-path-enrollments"))

    # --- webhooks and event payloads ----------------------------------------------------

    def list_webhooks(self, *, page: int | None = None,
                      page_size: int | None = None) -> Envelope:
        """CARRIES SECRETS in three places. See `_tools/events.py`; the tool redacts."""
        return parse_page(self._get("/v1/webhooks",
                                    {"page": page, "page_size": page_size}))

    def get_webhook(self, *, webhook_id: str) -> Envelope:
        """CARRIES SECRETS. See `_tools/events.py`."""
        return parse_page(self._get(f"/v1/webhooks/{webhook_id}"))

    def get_sample_event_payload(self, *, slug: str) -> Envelope:
        """One of the ten `/v1/webhooks/sample-*` endpoints, chosen by slug."""
        return parse_page(self._get(f"/v1/webhooks/sample-{slug}"))

    # --- instructor-led training (v2 has no ILT/vILT surface) ---------------------------

    def list_ilt_instructors(self, *, email: str | None = None,
                             provider: str | None = None, page: int | None = None,
                             page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/ilt-instructors", {
            "email": email, "provider": provider,
            "page": page, "page_size": page_size}))

    def list_ilt_sessions(self, *, page: int | None = None,
                          page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/ilt-sessions",
                                    {"page": page, "page_size": page_size}))

    def list_vilt_session_events(self, *, starts_after: str | None = None,
                                 ends_before: str | None = None,
                                 lesson_id: str | None = None,
                                 course_id: str | None = None,
                                 page: int | None = None,
                                 page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/vilt-session-events", {
            "starts_at__gte": starts_after, "ends_at__lte": ends_before,
            "session__lesson__id": lesson_id,
            "session__lesson__course__id": course_id,
            "page": page, "page_size": page_size}))

    def list_vilt_registrations(self, *, session_id: str | None = None,
                                page: int | None = None,
                                page_size: int | None = None) -> Envelope:
        """CARRIES LEARNER PII - name and email on every row."""
        return parse_page(self._get("/v1/vilt-session-registrations", {
            "session__id": session_id, "page": page, "page_size": page_size}))

    # --- labels, tags and group categories (the last v1 family) -------------------------

    def list_labels(self, *, page: int | None = None,
                    page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/labels",
                                    {"page": page, "page_size": page_size}))

    def list_tags(self, *, page: int | None = None,
                  page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/tags",
                                    {"page": page, "page_size": page_size}))

    def list_group_categories(self, *, page: int | None = None,
                              page_size: int | None = None) -> Envelope:
        return parse_page(self._get("/v1/group-categories",
                                    {"page": page, "page_size": page_size}))

    def list_course_labels(self, *, course_id: str) -> Envelope:
        return parse_page(self._get(f"/v1/courses/{course_id}/labels"))

    def find_learner(self, *, email: str) -> Envelope:
        """Resolve an email to a learner id, using the DRF-enveloped `/v1/users`.

        Kept because it is the other envelope shape, and because a caller holding only an
        email would otherwise have to reach into v2 to start a v1 call.
        """
        return parse_page(self._get("/v1/users", {"email": email}))


class FakeV1Backend:
    """In-memory v1 double. Holds RAW v1 payloads, not normalised ones.

    Deliberate: it stores the bare array and the DRF envelope exactly as Skilljar sends
    them, and runs them through the same `parse_page` the real backend uses. A double
    that stored the normalised shape would never exercise the normalisation, and the
    two-envelope trap is the single most likely thing to break here.
    """

    def __init__(self, users: list[dict[str, Any]] | None = None,
                 progress: dict[str, list[dict[str, Any]]] | None = None,
                 assets: list[dict[str, Any]] | None = None,
                 promo_codes: list[dict[str, Any]] | None = None,
                 promo_code_pools: list[dict[str, Any]] | None = None,
                 offers: list[dict[str, Any]] | None = None,
                 credit_codes: list[dict[str, Any]] | None = None,
                 purchases: list[dict[str, Any]] | None = None,
                 paths: list[dict[str, Any]] | None = None,
                 path_items: dict[str, list[dict[str, Any]]] | None = None,
                 published_paths: list[dict[str, Any]] | None = None,
                 course_series: list[dict[str, Any]] | None = None,
                 path_enrollments: dict[str, list[dict[str, Any]]] | None = None,
                 webhooks: list[dict[str, Any]] | None = None,
                 samples: dict[str, Any] | None = None,
                 instructors: list[dict[str, Any]] | None = None,
                 ilt_sessions: list[dict[str, Any]] | None = None,
                 vilt_events: list[dict[str, Any]] | None = None,
                 vilt_registrations: list[dict[str, Any]] | None = None,
                 labels: list[dict[str, Any]] | None = None,
                 tags: list[dict[str, Any]] | None = None,
                 group_categories: list[dict[str, Any]] | None = None,
                 course_labels: dict[str, list[dict[str, Any]]] | None = None) -> None:
        import copy
        # `users` is stored in the DRF shape: the learner NESTS under `user`, which is
        # what the real listing does and what a reader looking for a top-level `id`
        # misses entirely.
        self._users = copy.deepcopy(list(users or []))
        # user_id -> the learner's enrolments, as the BARE ARRAY the real endpoint sends.
        self._progress = copy.deepcopy(dict(progress or {}))
        # Stored WITH download_url; the listing strips it, exactly as the API does.
        self._assets = copy.deepcopy(list(assets or []))
        self._promo_codes = copy.deepcopy(list(promo_codes or []))
        self._promo_code_pools = copy.deepcopy(list(promo_code_pools or []))
        self._offers = copy.deepcopy(list(offers or []))
        self._credit_codes = copy.deepcopy(list(credit_codes or []))
        self._purchases = copy.deepcopy(list(purchases or []))
        self._paths = copy.deepcopy(list(paths or []))
        self._path_items = copy.deepcopy(dict(path_items or {}))
        self._published_paths = copy.deepcopy(list(published_paths or []))
        self._course_series = copy.deepcopy(list(course_series or []))
        self._path_enrollments = copy.deepcopy(dict(path_enrollments or {}))
        # Stored WITH their secrets, exactly as the API returns them. A fake that
        # pre-redacted would hide the whole point of the tool layer.
        self._webhooks = copy.deepcopy(list(webhooks or []))
        self._samples = copy.deepcopy(dict(samples or {}))
        self._instructors = copy.deepcopy(list(instructors or []))
        self._ilt_sessions = copy.deepcopy(list(ilt_sessions or []))
        self._vilt_events = copy.deepcopy(list(vilt_events or []))
        # Carries learner name and email on every row, as the real endpoint does.
        self._vilt_registrations = copy.deepcopy(list(vilt_registrations or []))
        self._labels = copy.deepcopy(list(labels or []))
        self._tags = copy.deepcopy(list(tags or []))
        self._group_categories = copy.deepcopy(list(group_categories or []))
        self._course_labels = copy.deepcopy(dict(course_labels or {}))

    def __repr__(self) -> str:
        return f"FakeV1Backend(users={len(self._users)})"

    def list_assets(self, *, page: int | None = None) -> Envelope:
        # The DRF envelope, and deliberately WITHOUT download_url on any row - the real
        # listing does not carry it, and a fake that did would hide trap 3 entirely.
        rows = [{k: v for k, v in a.items() if k != "download_url"} for a in self._assets]
        return parse_page({"count": len(rows), "next": None, "previous": None,
                           "results": rows})

    def get_asset(self, *, asset_id: str) -> Envelope:
        for a in self._assets:
            if a.get("id") == asset_id:
                # A single object, as the real detail endpoint returns - not an envelope.
                return parse_page(dict(a))
        raise exc.NotFoundError(f"v1 returned 404 for /v1/assets/{asset_id}. Either the "
                                f"record does not exist, or this endpoint is not served.")

    def _commerce_page(self, rows: list[dict[str, Any]], page: int | None,
                       page_size: int | None) -> Envelope:
        """v1 pages by NUMBER with a total, and honours page_size. Modelled faithfully
        because these are the families where paging actually happens - 13,708 promo
        codes is 55 pages at the server's default of 250."""
        size = page_size or 250
        start = ((page or 1) - 1) * size
        window = rows[start:start + size]
        more = start + size < len(rows)
        return parse_page({
            "count": len(rows),
            "next": f"https://api.skilljar.com/v1/x?page={(page or 1) + 1}" if more else None,
            "previous": None, "results": window})

    def list_promo_codes(self, *, active=None, code=None, promo_code_pool_id=None,
                         page=None, page_size=None) -> Envelope:
        rows = self._promo_codes
        if active is not None:
            rows = [r for r in rows if bool(r.get("active")) is bool(active)]
        if code is not None:
            rows = [r for r in rows if r.get("code") == code]
        if promo_code_pool_id is not None:
            rows = [r for r in rows if r.get("promo_code_pool_id") == promo_code_pool_id]
        return self._commerce_page(rows, page, page_size)

    def list_promo_code_pools(self, *, name=None, offer_id=None, page=None,
                              page_size=None) -> Envelope:
        rows = self._promo_code_pools
        if name is not None:
            rows = [r for r in rows if r.get("name") == name]
        return self._commerce_page(rows, page, page_size)

    def list_offers(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._offers, page, page_size)

    def list_training_credit_codes(self, *, tracking_identifier=None,
                                   training_credit_code=None, page=None,
                                   page_size=None) -> Envelope:
        rows = self._credit_codes
        if tracking_identifier is not None:
            rows = [r for r in rows if r.get("tracking_identifier") == tracking_identifier]
        if training_credit_code is not None:
            rows = [r for r in rows if r.get("training_credit_code") == training_credit_code]
        return self._commerce_page(rows, page, page_size)

    def get_purchase(self, *, purchase_id: str) -> Envelope:
        for r in self._purchases:
            if r.get("id") == purchase_id:
                return parse_page(dict(r))
        raise exc.NotFoundError(f"v1 returned 404 for /v1/purchases/{purchase_id}.")

    def list_ilt_instructors(self, *, email=None, provider=None, page=None,
                             page_size=None) -> Envelope:
        rows = self._instructors
        if email is not None:
            rows = [r for r in rows if r.get("email") == email]
        if provider is not None:
            rows = [r for r in rows if provider in (r.get("providers") or [])]
        return self._commerce_page(rows, page, page_size)

    def list_ilt_sessions(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._ilt_sessions, page, page_size)

    def list_vilt_session_events(self, *, starts_after=None, ends_before=None,
                                 lesson_id=None, course_id=None, page=None,
                                 page_size=None) -> Envelope:
        rows = self._vilt_events
        if starts_after is not None:
            rows = [r for r in rows if str(r.get("starts_at", "")) >= starts_after]
        if ends_before is not None:
            rows = [r for r in rows if str(r.get("ends_at", "")) <= ends_before]
        return self._commerce_page(rows, page, page_size)

    def list_vilt_registrations(self, *, session_id=None, page=None,
                                page_size=None) -> Envelope:
        rows = self._vilt_registrations
        if session_id is not None:
            rows = [r for r in rows
                    if (r.get("vilt_session") or {}).get("id") == session_id]
        return self._commerce_page(rows, page, page_size)

    def list_labels(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._labels, page, page_size)

    def list_tags(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._tags, page, page_size)

    def list_group_categories(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._group_categories, page, page_size)

    def list_course_labels(self, *, course_id: str) -> Envelope:
        return parse_page(self._course_labels.get(course_id, []))

    def list_webhooks(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._webhooks, page, page_size)

    def get_webhook(self, *, webhook_id: str) -> Envelope:
        for w in self._webhooks:
            if w.get("id") == webhook_id:
                return parse_page(dict(w))
        raise exc.NotFoundError(f"v1 returned 404 for /v1/webhooks/{webhook_id}.")

    def get_sample_event_payload(self, *, slug: str) -> Envelope:
        if slug not in self._samples:
            raise exc.NotFoundError(f"v1 returned 404 for /v1/webhooks/sample-{slug}.")
        # A LIST of one, which is what the real endpoint sends - verified live. A fake
        # returning the bare object would have let `parse_page` reject the real shape.
        return parse_page({"results": [self._samples[slug]]})

    def list_paths(self, *, page=None, page_size=None) -> Envelope:
        return self._commerce_page(self._paths, page, page_size)

    def get_path(self, *, path_id: str) -> Envelope:
        for r in self._paths:
            if r.get("id") == path_id:
                return parse_page(dict(r))
        raise exc.NotFoundError(f"v1 returned 404 for /v1/paths/{path_id}.")

    def list_path_items(self, *, path_id: str, page=None, page_size=None) -> Envelope:
        self.get_path(path_id=path_id)
        return self._commerce_page(self._path_items.get(path_id, []), page, page_size)

    def list_published_paths(self, *, domain_name: str, page=None,
                             page_size=None) -> Envelope:
        rows = [r for r in self._published_paths
                if r.get("_domain", domain_name) == domain_name]
        return self._commerce_page(rows, page, page_size)

    def list_course_series(self, *, domain_name: str, page=None,
                           page_size=None) -> Envelope:
        return self._commerce_page(self._course_series, page, page_size)

    def list_learner_path_enrollments(self, *, user_id: str) -> Envelope:
        return parse_page(self._path_enrollments.get(user_id, []))

    def find_learner(self, *, email: str) -> Envelope:
        rows = [u for u in self._users
                if str(u.get("user", {}).get("email", "")).lower() == email.lower()]
        # The DRF envelope, verbatim - including `count`, which v2 never provides.
        return parse_page({"count": len(rows), "next": None, "previous": None,
                           "results": rows})

    def list_learner_progress(self, *, user_id: str,
                              page: int | None = None) -> Envelope:
        if user_id not in self._progress:
            raise exc.NotFoundError(f"v1 returned 404 for /v1/users/{user_id}"
                                    f"/published-courses. Either the record does not "
                                    f"exist, or this endpoint is not served.")
        # A BARE ARRAY, as the real endpoint sends. No count, no next.
        return parse_page(self._progress[user_id])

    def get_learner_progress(self, *, user_id: str,
                             published_course_id: str) -> Envelope:
        """Selects from the list, exactly as `V1Backend` does and for the same reason."""
        listing = self.list_learner_progress(user_id=user_id)
        for row in listing["rows"]:
            if row.get("published_course_id") == published_course_id:
                return {"rows": [row], "total": 1, "has_more": False, "next_page": None}
        raise exc.NotFoundError(
            f"learner {user_id} has no enrolment in published course "
            f"{published_course_id}. They have {len(listing['rows'])} enrolments; "
            f"list_learner_progress shows them.")
