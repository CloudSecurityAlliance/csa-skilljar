"""Exit-code contract for the dashboard drift checker.

There is no OpenAPI document for the dashboard's DataTables/HTML endpoints, so the
contract is asserted by hand in `evaluate()`. `main()` additionally has to tell three
outcomes apart - healthy, drift, and "could not check" - because issue #13 filed a
transport timeout as upstream drift and it sat open for five days while real drift went
unnoticed. An outage or an expired session must never look like a finding.

Pure unit tests - `_fetch` and `DashboardSession.from_file` are replaced, so nothing
here touches the network or the filesystem.
"""
import importlib.util
import pathlib
import sys

SPEC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_dashboard.py"
_spec = importlib.util.spec_from_file_location("check_dashboard", SPEC)
assert _spec and _spec.loader
cd = importlib.util.module_from_spec(_spec)
sys.modules["check_dashboard"] = cd
_spec.loader.exec_module(cd)

GOOD = {"recordsTotal": 5, "data": [{
    "type": {"display": '<a href="/tasks/grade-quiz/t1">Quiz Response</a>',
             "sort": "", "filter": ""},
    "submitted_at": {"display": "", "sort": "", "filter": ""},
    "completed_at": {"display": "", "sort": "", "filter": ""},
    "course": {"display": "", "sort": "", "filter": ""},
    "student_name": {"display": "", "sort": "", "filter": ""},
    "student_email": {"display": "", "sort": "", "filter": ""}}]}

GOOD_FORM = ('<input name="csrfmiddlewaretoken" value="t">'
             '<input name="quiz_response_id">'
             '<input name="email_student_on_completion">'
             '<input name="question-response-q1-correct">')


def test_a_healthy_response_reports_nothing():
    assert cd.evaluate(GOOD, GOOD_FORM) == []


def test_a_missing_column_is_reported():
    bad = {"recordsTotal": 1, "data": [{k: v for k, v in GOOD["data"][0].items()
                                        if k != "student_email"}]}
    assert any("student_email" in p for p in cd.evaluate(bad, GOOD_FORM))


def test_a_changed_anchor_is_reported():
    bad = {"recordsTotal": 1, "data": [{**GOOD["data"][0],
           "type": {"display": "<a href=/elsewhere>x</a>", "sort": "", "filter": ""}}]}
    assert any("grade-quiz" in p for p in cd.evaluate(bad, GOOD_FORM))


def test_a_grading_form_without_its_fields_is_reported():
    problems = cd.evaluate(GOOD, "<form></form>")
    assert any("csrfmiddlewaretoken" in p for p in problems)
    assert any("quiz_response_id" in p for p in problems)


# --- main(): the three outcomes must stay distinguishable ---------------------------

def _good_fetch(url, cookies):
    if "/tasks/ajax" in url:
        import json
        return 200, "application/json", json.dumps(GOOD).encode()
    return 200, "text/html", GOOD_FORM.encode()


def _fake_session(monkeypatch, tmp_path):
    """A session file that loads cleanly, without touching real disk-loading logic
    beyond what DashboardSession.from_file itself does."""
    import json as _json
    p = tmp_path / "session.json"
    p.write_text(_json.dumps(
        {"cookies": [{"name": "sj_sessionid", "value": "x", "domain": "dashboard.skilljar.com"}]}))
    monkeypatch.setenv(cd.DASHBOARD_SESSION_VAR, str(p))


def test_no_session_var_is_uncheckable_not_a_finding(monkeypatch, capsys):
    monkeypatch.delenv(cd.DASHBOARD_SESSION_VAR, raising=False)
    assert cd.main() == cd.EXIT_UNCHECKABLE
    err = capsys.readouterr().err
    assert "COULD NOT CHECK" in err
    assert cd.DASHBOARD_SESSION_VAR in err


def test_a_healthy_dashboard_exits_zero(monkeypatch, tmp_path, capsys):
    _fake_session(monkeypatch, tmp_path)
    monkeypatch.setattr(cd, "_fetch", _good_fetch)
    assert cd.main() == cd.EXIT_OK
    assert "no drift" in capsys.readouterr().out


def test_drift_exits_one_and_lists_problems(monkeypatch, tmp_path, capsys):
    _fake_session(monkeypatch, tmp_path)

    def fetch(url, cookies):
        if "/tasks/ajax" in url:
            import json
            bad = {"recordsTotal": 1, "data": [{k: v for k, v in GOOD["data"][0].items()
                                                if k != "student_email"}]}
            return 200, "application/json", json.dumps(bad).encode()
        return 200, "text/html", GOOD_FORM.encode()

    monkeypatch.setattr(cd, "_fetch", fetch)
    assert cd.main() == cd.EXIT_DRIFT
    assert "student_email" in capsys.readouterr().err


def test_an_unreachable_dashboard_exits_two_not_one(monkeypatch, tmp_path, capsys):
    """The distinction that matters: exit 1 means the dashboard moved, exit 2 means we
    could not find out. See issue #13."""
    _fake_session(monkeypatch, tmp_path)

    def fetch(url, cookies):
        raise cd.Unreachable(f"could not reach {url}: timeout")

    monkeypatch.setattr(cd, "_fetch", fetch)
    assert cd.main() == cd.EXIT_UNCHECKABLE
    err = capsys.readouterr().err
    assert "UNREACHABLE" in err
    assert "not a finding" in err


def test_an_expired_session_exits_two_and_names_the_capture_script(monkeypatch, tmp_path, capsys):
    _fake_session(monkeypatch, tmp_path)

    def fetch(url, cookies):
        return 302, "text/html", b""

    monkeypatch.setattr(cd, "_fetch", fetch)
    assert cd.main() == cd.EXIT_UNCHECKABLE
    err = capsys.readouterr().err
    assert "expired" in err
    assert "capture_dashboard_session.py" in err


def test_an_unloadable_session_file_is_uncheckable(monkeypatch, tmp_path, capsys):
    p = tmp_path / "session.json"
    p.write_text("not json")
    monkeypatch.setenv(cd.DASHBOARD_SESSION_VAR, str(p))
    assert cd.main() == cd.EXIT_UNCHECKABLE
    assert "COULD NOT CHECK" in capsys.readouterr().err


def test_missing_task_id_still_reports_grading_form_problems(monkeypatch, tmp_path, capsys):
    """No task id to probe the grading page with is not itself uncheckable - `evaluate`
    still has an empty-string grading_html to check the listing row against, and reports
    the (many) resulting problems as drift."""
    _fake_session(monkeypatch, tmp_path)
    no_anchor = {"recordsTotal": 1, "data": [{**GOOD["data"][0],
                 "type": {"display": "no anchor here", "sort": "", "filter": ""}}]}

    def fetch(url, cookies):
        import json
        assert "/tasks/ajax" in url, "the grading page should never be fetched"
        return 200, "application/json", json.dumps(no_anchor).encode()

    monkeypatch.setattr(cd, "_fetch", fetch)
    assert cd.main() == cd.EXIT_DRIFT
