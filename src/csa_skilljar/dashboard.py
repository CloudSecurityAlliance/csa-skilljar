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
# Shared by `UnconfiguredDashboard` (below) and `SkilljarClient._require_dashboard`, so the
# two paths that can report "no session" say exactly the same thing.
NO_SESSION_MESSAGE = (
    "this capability exists only in the Skilljar dashboard, which needs a session. "
    f"{_CAPTURE_HINT} Then set CSA_SKILLJAR_DASHBOARD_SESSION to the file it writes and "
    "restart. Call `check_access` to see what is available.")


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
_CSRF = re.compile(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"')
_QUIZ_RESPONSE = re.compile(r'name="quiz_response_id"[^>]*value="([^"]*)"')
_QUESTION_IDS = re.compile(r'name="question-response-([A-Za-z0-9]+)-correct"')
_PROMPT = re.compile(r"Question:\s*(.{0,400}?)\s*<", re.S)
_RESPONSE = re.compile(r'name="student_response_text"[^>]*>(.*?)</textarea>', re.S)
_STATUSES = ("pending", "completed", "all")


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
        # Same status check, same order, as `_get_html`: identical inputs must produce
        # identical outcomes in both methods. A redirect here is the login page, and it
        # must be reported as an expired session - not, once it fails the content-type
        # check below, as "the endpoint changed".
        if r.status_code in (301, 302, 401, 403):
            raise exc.CredentialsMissing(
                f"the dashboard session is not valid or has expired. {_CAPTURE_HINT}")
        ctype = r.headers.get("content-type", "").split(";")[0]
        if ctype != "application/json":
            # Not a redirect (that was ruled out above) - so a genuine shape change.
            raise exc.UpstreamChanged(
                f"{path} returned {ctype or 'no content-type'} where JSON was expected; "
                f"the endpoint has changed. Run scripts/check_dashboard.py.")
        return r.json()

    def _get_html(self, path: str) -> str:
        try:
            r = self._http.get(f"{self._base}{path}", cookies=self._session.cookies(),
                               follow_redirects=False)
        except httpx.HTTPError as e:
            raise exc.ApiError(f"could not reach the Skilljar dashboard: {e}") from e
        # A redirect here is the login page. 302 and 401 mean the same thing to a caller.
        if r.status_code in (301, 302, 401, 403):
            raise exc.CredentialsMissing(
                f"the dashboard session is not valid or has expired. {_CAPTURE_HINT}")
        return r.text

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
        """One page of the grading queue.

        `total` is the GLOBAL count (`recordsTotal`, the whole queue, every status).
        `pending_on_page`/`completed_on_page` are counted from the rows THIS page
        returned - never the whole queue - because the DataTables endpoint gives no
        per-status total, only a per-page one. Against the real org (661 total, 30
        pending) page one can report `pending_on_page` no higher than `page_size`, which
        is why the field says "on_page" rather than implying a queue-wide count.
        """
        if status not in _STATUSES:
            raise exc.ApiError(
                f"unrecognised status {status!r}; must be one of "
                f"{', '.join(_STATUSES)}.")
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
        # status is validated above; "all" (and nothing else) falls through to every row.
        chosen = {"pending": pending, "completed": completed}.get(status, rows)
        return {"tasks": chosen, "total": payload.get("recordsTotal", len(rows)),
                "pending_on_page": len(pending), "completed_on_page": len(completed)}

    def get_task(self, *, id: str) -> dict[str, Any]:
        """One task, with the questions awaiting grading.

        Returns `csrf_token` because the grading POST needs it and it is obtainable ONLY
        from this GET: the form token is a masked value and does NOT equal the
        `sj_csrftoken` cookie. Measured against the live dashboard, 2026-09-02.
        """
        import html as _html
        page = self._get_html(f"/tasks/grade-quiz/{id}")
        tok = _CSRF.search(page)
        if not tok:
            raise exc.UpstreamChanged(
                "the grading page carried no csrfmiddlewaretoken, so its form contract "
                "has changed. Run scripts/check_dashboard.py.")
        qr = _QUIZ_RESPONSE.search(page)
        question_ids = list(dict.fromkeys(_QUESTION_IDS.findall(page)))
        prompts = [_html.unescape(_TAGS.sub(" ", p)).strip() for p in _PROMPT.findall(page)]
        responses = [_html.unescape(_TAGS.sub(" ", r)).strip() for r in _RESPONSE.findall(page)]
        # Positional pairing is only safe if all three lists agree in length. If the page
        # returns more of one than another, positional indexing would silently pair a
        # question with the WRONG prompt or response - on a page that decides a
        # certification. That must be loud, not a best-effort guess.
        if not (len(question_ids) == len(prompts) == len(responses)):
            raise exc.UpstreamChanged(
                f"the grading page has {len(question_ids)} question id(s), "
                f"{len(prompts)} prompt(s) and {len(responses)} response(s); these must "
                f"match to pair them safely. Its form contract has changed. Run "
                f"scripts/check_dashboard.py.")
        questions = [
            {"question_id": qid, "prompt": prompt, "response": response}
            for qid, prompt, response in zip(question_ids, prompts, responses, strict=True)
        ]
        return {"id": id, "csrf_token": tok.group(1),
                "quiz_response_id": qr.group(1) if qr else None,
                "questions": questions}


class FakeDashboard(DashboardBackend):
    """In-memory double storing RAW `/ajax` payload shapes.

    Subclasses the real backend so the PARSING is exercised rather than bypassed - only
    the transport is replaced. A fake that stored parsed rows would let a parser bug pass
    every offline test.
    """

    def __init__(self, tasks: list[dict[str, Any]] | None = None,
                 pages: dict[str, str] | None = None) -> None:
        import copy
        self._raw = copy.deepcopy(list(tasks or []))
        self._pages = dict(pages or {})
        self._session = DashboardSession({SESSION_COOKIE: "fake"})
        self._base = DEFAULT_BASE
        self._http = None

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        start = int(params.get("start", 0)); length = int(params.get("length", 25))
        window = self._raw[start:start + length]
        return {"recordsTotal": len(self._raw), "recordsFiltered": len(self._raw),
                "data": window}

    def _get_html(self, path: str) -> str:
        if path not in self._pages:
            raise exc.NotFoundError(f"no fake page for {path}")
        return self._pages[path]


class UnconfiguredDashboard:
    """Stands in for a real `DashboardBackend` when no session is configured, or a
    configured one could not be loaded - so the CAPABILITY GATE runs before this ever
    executes.

    `PolicyBackend.__getattr__` (see `policy.py`) checks `_GATES` and the active policy
    BEFORE delegating to the wrapped backend at all. Previously the credential prompt sat
    in `SkilljarClient._require_dashboard`, which fired the instant `self._dashboard is
    None` - so it ran unconditionally, with no policy in the loop. Under the default
    `parity` profile (which does not grant `tasks.read`) that told a caller to go capture
    a full-privilege admin session cookie, and only after following the instruction and
    restarting did they learn the capability was refused all along.

    `mcp/_config.py` wraps an instance of THIS class in the same `PolicyBackend` a real
    `DashboardBackend` would get, so `ClientProvider` never hands out a bare `None`
    dashboard: the profile refusal answers first in every case. Reaching one of these
    methods means the policy allows `tasks.read` but there is no usable session yet -
    which is exactly when the capture instruction is the right thing to say.
    """

    def list_tasks(self, **kw: Any) -> dict[str, Any]:
        raise exc.CredentialsMissing(NO_SESSION_MESSAGE)

    def get_task(self, **kw: Any) -> dict[str, Any]:
        raise exc.CredentialsMissing(NO_SESSION_MESSAGE)
