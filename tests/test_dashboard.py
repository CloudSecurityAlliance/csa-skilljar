import json

import httpx
import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.dashboard import DashboardBackend, DashboardSession

SESSION = {"cookies": [
    {"name": "sj_sessionid", "value": "sess-abc", "domain": "dashboard.skilljar.com"},
    {"name": "sj_csrftoken", "value": "csrf-xyz", "domain": "dashboard.skilljar.com"},
    {"name": "unrelated", "value": "x", "domain": "example.com"},
]}


def test_a_session_file_yields_only_skilljar_cookies(tmp_path):
    f = tmp_path / "s.json"; f.write_text(json.dumps(SESSION))
    s = DashboardSession.from_file(str(f))
    assert s.cookies() == {"sj_sessionid": "sess-abc", "sj_csrftoken": "csrf-xyz"}


def test_a_missing_file_is_a_credential_problem_not_an_oserror(tmp_path):
    with pytest.raises(exc.CredentialsMissing) as e:
        DashboardSession.from_file(str(tmp_path / "absent.json"))
    assert "capture" in str(e.value).lower()


def test_a_file_without_the_session_cookie_is_refused(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"cookies": [
        {"name": "sj_csrftoken", "value": "c", "domain": "dashboard.skilljar.com"}]}))
    with pytest.raises(exc.CredentialsMissing) as e:
        DashboardSession.from_file(str(f))
    assert "sj_sessionid" in str(e.value)


def test_the_repr_never_carries_a_cookie_value(tmp_path):
    f = tmp_path / "s.json"; f.write_text(json.dumps(SESSION))
    r = repr(DashboardSession.from_file(str(f)))
    assert "sess-abc" not in r and "csrf-xyz" not in r
    assert "redacted" in r


def _cell(html):                       # the /ajax cell shape
    return {"display": html, "sort": html, "filter": html}


ROW = {
    "type": _cell('<a href="/tasks/grade-quiz/tsk1?next=%2Ftasks%2F">Quiz Response</a>'),
    "submitted_at": _cell('<span class="nowrap">2025-Aug-03</span>'),
    "completed_at": _cell('<span class="nowrap">--</span>'),
    "course": _cell('<div><a href="/course/crs1/">CCSK TTT</a> / '
                    '<a href="/course/crs1/les1">Lab 3.2</a></div>'),
    "student_name": _cell("Ada Lovelace"),
    "student_email": _cell("ada@example.org"),
}
DONE_ROW = {**ROW, "completed_at": _cell('<span class="nowrap">2025-Sep-01</span>')}


def _backend(payload, capture=None):
    def handler(request):
        if capture is not None:
            capture.append(request)
        return httpx.Response(200, json=payload)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return DashboardBackend(DashboardSession({"sj_sessionid": "s"}), http=http)


def test_a_row_is_parsed_into_flat_fields():
    b = _backend({"recordsTotal": 2, "recordsFiltered": 2, "data": [ROW, DONE_ROW]})
    got = b.list_tasks(status="all")
    t = got["tasks"][0]
    assert t["id"] == "tsk1"
    assert t["type"] == "Quiz Response"
    assert t["submitted_at"] == "2025-Aug-03"
    assert t["completed_at"] is None          # '--' means not graded
    assert t["course_id"] == "crs1"
    assert t["course_title"] == "CCSK TTT"
    assert t["lesson_id"] == "les1"
    assert t["lesson_title"] == "Lab 3.2"
    assert t["student_email"] == "ada@example.org"


def test_counts_are_reported_separately():
    """661 total with 30 pending reads as a 661-item backlog unless both are stated."""
    b = _backend({"recordsTotal": 2, "recordsFiltered": 2, "data": [ROW, DONE_ROW]})
    got = b.list_tasks(status="all")
    assert got["total"] == 2 and got["pending"] == 1 and got["completed"] == 1


def test_pending_is_the_default_and_filters():
    b = _backend({"recordsTotal": 2, "recordsFiltered": 2, "data": [ROW, DONE_ROW]})
    got = b.list_tasks()
    assert [t["id"] for t in got["tasks"]] == ["tsk1"]


def test_the_request_carries_the_datatables_parameters():
    cap = []
    b = _backend({"recordsTotal": 0, "recordsFiltered": 0, "data": []}, cap)
    b.list_tasks(page=3, page_size=50)
    q = dict(httpx.URL(str(cap[0].url)).params)
    assert q["start"] == "100" and q["length"] == "50"
    assert cap[0].url.path == "/tasks/ajax"


def test_an_unrecognised_anchor_raises_rather_than_returning_none():
    """ZD-2. A changed link shape must be loud; a task with id None would flow onward
    and fail later somewhere that cannot explain itself."""
    bad = {**ROW, "type": _cell("<a href=/somewhere/else>Quiz Response</a>")}
    b = _backend({"recordsTotal": 1, "recordsFiltered": 1, "data": [bad]})
    with pytest.raises(exc.UpstreamChanged):
        b.list_tasks(status="all")


def test_html_where_json_was_expected_is_upstream_changed():
    """A login redirect returns HTML. Parsed as data it looks like an empty queue."""
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text="<html>log in</html>",
                                 headers={"content-type": "text/html"})))
    b = DashboardBackend(DashboardSession({"sj_sessionid": "s"}), http=http)
    with pytest.raises(exc.UpstreamChanged):
        b.list_tasks()
