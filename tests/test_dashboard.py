import json

import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.dashboard import DashboardSession

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
