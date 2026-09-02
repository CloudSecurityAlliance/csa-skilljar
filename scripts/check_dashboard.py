#!/usr/bin/env python3
"""Detect drift in the dashboard's undocumented endpoints.

`check_upstream.py` diffs OpenAPI documents. There is no such document here - the
dashboard backend (`csa_skilljar/dashboard.py`) reads two undocumented, unversioned
endpoints by scraping a DataTables JSON payload and an HTML form. Without a hand-written
contract check, a Skilljar UI release surfaces as an empty task list: a grading queue
that looks clear when it is not.

Unreachable and changed are reported DIFFERENTLY, and so is "no session to check with".
Issue #13 filed a TLS handshake timeout as upstream drift, and it sat open for five days
while real drift went unnoticed. A check that reports "no problems" when it could not
reach the target - or had no live session to test with - is worse than no check.

Needs a live, logged-in dashboard session (`scripts/capture_dashboard_session.py`), so
this cannot run unattended in CI - see the row in OPERATIONAL-RESOURCES.md.

Run:  .venv/bin/python scripts/check_dashboard.py
Exit: 0 healthy · 1 drift detected · 2 could not check (unreachable, or no usable session)
"""
from __future__ import annotations

import json
import os
import re
import sys

import httpx

from csa_skilljar import exceptions as exc
from csa_skilljar.dashboard import DashboardSession
from csa_skilljar.mcp._config import DASHBOARD_SESSION_VAR

BASE = "https://dashboard.skilljar.com"
TIMEOUT = 30.0

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNCHECKABLE = 2

# A looser, local copy of dashboard.py's `_TASK_ID` - good enough to find ONE task id to
# probe the grading page with. Not used to judge correctness; `evaluate()` does that.
_TASK_ID = re.compile(r"/tasks/grade-quiz/([A-Za-z0-9]+)")

EXPECTED_COLUMNS = ["type", "submitted_at", "completed_at", "course",
                    "student_name", "student_email"]
EXPECTED_FORM_FIELDS = ["csrfmiddlewaretoken", "quiz_response_id",
                        "email_student_on_completion"]


class Unreachable(Exception):
    """The dashboard could not be reached at all. An infrastructure problem, NOT a
    finding - see the module docstring and issue #13."""


def evaluate(payload: dict, grading_html: str) -> list[str]:
    """Pure. Returns a problem list; empty means healthy."""
    problems: list[str] = []
    rows = payload.get("data") or []
    if not rows:
        problems.append("/tasks/ajax returned no rows, so its shape cannot be checked")
        return problems
    row = rows[0]
    for col in EXPECTED_COLUMNS:
        if col not in row:
            problems.append(f"/tasks/ajax row is missing the `{col}` column")
            continue
        cell = row[col]
        if not (isinstance(cell, dict) and {"display", "sort", "filter"} <= set(cell)):
            problems.append(f"`{col}` is no longer a display/sort/filter cell")
    anchor = str(row.get("type", {}).get("display", ""))
    if "/tasks/grade-quiz/" not in anchor:
        problems.append("the task id is no longer in a /tasks/grade-quiz/ anchor")
    for field in EXPECTED_FORM_FIELDS:
        if field not in grading_html:
            problems.append(f"the grading form no longer carries `{field}`")
    if "question-response-" not in grading_html:
        problems.append("the grading form has no question-response-* fields")
    return problems


def _fetch(url: str, cookies: dict[str, str]) -> tuple[int, str, bytes]:
    """GET `url` with the session cookies. Returns (status, content-type, body).

    Redirects are NOT followed: a redirect to the login page is the expired-session
    signal (see dashboard.py's own `_get_html`), and following it would turn that signal
    into a 200 for the login page instead.

    Only a transport-level failure raises - an HTTP status, including 401/403/302, is a
    RESULT to be interpreted by the caller, exactly as in `check_upstream.py`.
    """
    try:
        r = httpx.get(url, cookies=cookies, timeout=TIMEOUT, follow_redirects=False)
    except httpx.HTTPError as e:
        raise Unreachable(f"could not reach {url}: {e}") from e
    return r.status_code, r.headers.get("content-type", "").split(";")[0], r.content


def main() -> int:
    print("checking the Skilljar dashboard's undocumented endpoints\n")

    session_path = os.environ.get(DASHBOARD_SESSION_VAR)
    if not session_path:
        print(f"COULD NOT CHECK: {DASHBOARD_SESSION_VAR} is not set, so there is no "
              f"session to check with. Run scripts/capture_dashboard_session.py to get "
              f"one.", file=sys.stderr)
        return EXIT_UNCHECKABLE

    try:
        session = DashboardSession.from_file(session_path)
    except exc.CredentialsMissing as e:
        print(f"COULD NOT CHECK: {e}", file=sys.stderr)
        return EXIT_UNCHECKABLE
    cookies = session.cookies()

    try:
        status, ctype, body = _fetch(
            f"{BASE}/tasks/ajax?draw=1&start=0&length=25&skip_total_count=false", cookies)
    except Unreachable as e:
        print(f"UNREACHABLE: {e}\nThis is an infrastructure problem, not a finding about "
              f"the dashboard.", file=sys.stderr)
        return EXIT_UNCHECKABLE

    if status in (301, 302, 401, 403):
        print(f"COULD NOT CHECK: /tasks/ajax returned HTTP {status}; the dashboard "
              f"session has expired. Run scripts/capture_dashboard_session.py to get a "
              f"new one.", file=sys.stderr)
        return EXIT_UNCHECKABLE
    if status != 200 or ctype != "application/json":
        # Ambiguous: could be a changed endpoint (drift) or an expired session this
        # status-code check didn't catch. Per the module docstring, an ambiguous signal
        # is never reported as a finding.
        print(f"COULD NOT CHECK: /tasks/ajax returned HTTP {status} "
              f"{ctype or '(no content-type)'} where JSON was expected, so drift and an "
              f"expired session cannot be told apart. Re-run "
              f"scripts/capture_dashboard_session.py and try again.", file=sys.stderr)
        return EXIT_UNCHECKABLE

    try:
        payload = json.loads(body)
    except ValueError as e:
        print(f"COULD NOT CHECK: /tasks/ajax body is not valid JSON ({e})",
              file=sys.stderr)
        return EXIT_UNCHECKABLE

    grading_html = ""
    rows = payload.get("data") or []
    task_id = None
    if rows:
        anchor = str(rows[0].get("type", {}).get("display", ""))
        m = _TASK_ID.search(anchor)
        task_id = m.group(1) if m else None

    if task_id:
        try:
            g_status, _g_ctype, g_body = _fetch(f"{BASE}/tasks/grade-quiz/{task_id}", cookies)
        except Unreachable as e:
            print(f"UNREACHABLE: {e}\nThis is an infrastructure problem, not a finding "
                  f"about the dashboard.", file=sys.stderr)
            return EXIT_UNCHECKABLE
        if g_status in (301, 302, 401, 403):
            print(f"COULD NOT CHECK: the grading page returned HTTP {g_status}; the "
                  f"dashboard session has expired. Run "
                  f"scripts/capture_dashboard_session.py to get a new one.",
                  file=sys.stderr)
            return EXIT_UNCHECKABLE
        if g_status != 200:
            print(f"COULD NOT CHECK: the grading page returned HTTP {g_status}, "
                  f"so drift and an outage cannot be told apart.", file=sys.stderr)
            return EXIT_UNCHECKABLE
        grading_html = g_body.decode("utf-8", errors="replace")
    else:
        print("  no task id could be found in /tasks/ajax's first row; the grading form "
              "cannot be checked and its checks will report as missing", file=sys.stderr)

    problems = evaluate(payload, grading_html)
    print()
    if problems:
        print(f"DRIFT DETECTED ({len(problems)} findings):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nUpdate csa_skilljar/dashboard.py's parsing to match, and refresh the "
              "hand-written contract in this script.", file=sys.stderr)
        return EXIT_DRIFT
    print("no drift: the dashboard's undocumented endpoints match the expected shape")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
