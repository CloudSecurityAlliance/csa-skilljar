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
import re
from typing import Any

import httpx

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


_TASK_ID = re.compile(r"/tasks/grade-quiz/([A-Za-z0-9]+)")
_HREF_ID = re.compile(r'href="/course/([A-Za-z0-9]+)/([A-Za-z0-9]*)"')
_TAGS = re.compile(r"<[^>]+>")


def _text(cell: Any) -> str:
    """The visible text of a `{display, sort, filter}` cell."""
    import html as _html
    raw = cell.get("display", "") if isinstance(cell, dict) else str(cell)
    return _html.unescape(_TAGS.sub(" ", str(raw))).replace("\xa0", " ").strip()


class DashboardBackend:
    """Reads over the dashboard's DataTables endpoints. No writes in this step."""

    def __init__(self, session: DashboardSession, *, base_url: str = DEFAULT_BASE,
                 http: Any | None = None) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=_TIMEOUT)

    def __repr__(self) -> str:
        return f"DashboardBackend(base_url={self._base!r})"

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._http.get(f"{self._base}{path}", params=params,
                               cookies=self._session.cookies())
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach the Skilljar dashboard: {e}") from e
        if r.status_code in (401, 403):
            raise exc.CredentialsMissing(
                f"the dashboard session is not valid or has expired. {_CAPTURE_HINT}")
        ctype = r.headers.get("content-type", "").split(";")[0]
        if ctype != "application/json":
            # Almost always a redirect to the login page. Treated as data this would
            # look like an empty queue - the failure the whole class of check exists for.
            raise exc.UpstreamChanged(
                f"{path} returned {ctype or 'no content-type'} where JSON was expected; "
                f"the session may have expired or the endpoint changed. Run "
                f"scripts/check_dashboard.py.")
        return r.json()

    def _parse_task(self, row: dict[str, Any]) -> dict[str, Any]:
        anchor = str(row.get("type", {}).get("display", ""))
        m = _TASK_ID.search(anchor)
        if not m:
            raise exc.UpstreamChanged(
                "a task row carried no /tasks/grade-quiz/<id> link, so its id cannot be "
                "read. Run scripts/check_dashboard.py.")
        course_html = str(row.get("course", {}).get("display", ""))
        ids = _HREF_ID.findall(course_html)
        course_id = ids[0][0] if ids else None
        lesson_id = next((b for _, b in ids if b), None)
        titles = [t.strip() for t in _text(row.get("course", {})).split("/") if t.strip()]
        done = _text(row.get("completed_at", {}))
        return {
            "id": m.group(1),
            "type": _text(row.get("type", {})),
            "submitted_at": _text(row.get("submitted_at", {})) or None,
            "completed_at": None if done in ("", "--") else done,
            "course_id": course_id,
            "course_title": titles[0] if titles else None,
            "lesson_id": lesson_id,
            "lesson_title": titles[1] if len(titles) > 1 else None,
            "student_email": _text(row.get("student_email", {})) or None,
        }

    def list_tasks(self, *, status: str = "pending", page: int = 1,
                   page_size: int = 25) -> dict[str, Any]:
        payload = self._get_json("/tasks/ajax", {
            "draw": 1,
            "start": (max(page, 1) - 1) * page_size,
            "length": page_size,
            "skip_total_count": "false",
            "order[0][column]": 2,
            "order[0][dir]": "desc",
        })
        rows = [self._parse_task(r) for r in payload.get("data", [])]
        pending = [t for t in rows if t["completed_at"] is None]
        completed = [t for t in rows if t["completed_at"] is not None]
        chosen = {"pending": pending, "completed": completed}.get(status, rows)
        return {"tasks": chosen, "total": payload.get("recordsTotal", len(rows)),
                "pending": len(pending), "completed": len(completed)}
