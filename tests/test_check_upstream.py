"""Exit-code contract for the drift checker.

It gates a scheduled CI job that files issues, so "an outage looks like a finding" is a
real failure mode: the first scheduled run failed on a single transient SSL handshake
timeout among 34 sequential probes and reported identically to real drift. An outage
that looks like a finding trains people to ignore findings.

Pure unit tests - `_get` is replaced, so nothing here touches the network.
"""
import importlib.util
import pathlib
import sys

import pytest

SPEC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_upstream.py"
_spec = importlib.util.spec_from_file_location("check_upstream", SPEC)
assert _spec and _spec.loader
cu = importlib.util.module_from_spec(_spec)
sys.modules["check_upstream"] = cu
_spec.loader.exec_module(cu)


def _snapshot_matching_responses():
    """Responses identical to the committed snapshots, so a clean run means no drift."""
    import json
    root = pathlib.Path(__file__).resolve().parent.parent
    v2 = (root / "specs" / "skilljar-v2-openapi.json").read_bytes()
    az = (root / "analysis" / "live-authz-metadata.json").read_bytes()

    def fake_get(url: str):
        if url.endswith("/v2/openapi.json"):
            return 200, v2
        if "oauth-authorization-server" in url:
            return 200, az
        if url.endswith("/v2/courses/"):
            return 401, b""
        if "definitely-not-a-real-thing" in url:
            return 404, b""
        return 404, b""      # every reserved area still unbuilt
    return fake_get


def test_clean_run_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(cu, "_get", _snapshot_matching_responses())
    assert cu.main() == cu.EXIT_OK
    assert "no drift" in capsys.readouterr().out


def test_a_shipped_reserved_area_is_drift_not_an_outage(monkeypatch, capsys):
    base = _snapshot_matching_responses()

    def fake_get(url: str):
        if url.endswith("/v2/webhooks/"):
            return 401, b""          # it exists now
        return base(url)

    monkeypatch.setattr(cu, "_get", fake_get)
    assert cu.main() == cu.EXIT_DRIFT
    assert "webhooks" in capsys.readouterr().err


def test_an_outage_exits_two_not_one(monkeypatch, capsys):
    """The distinction that matters: exit 1 means Skilljar moved, exit 2 means we could
    not find out. The scheduled job files a drift issue only for exit 1."""
    def fake_get(url: str):
        raise cu.Unreachable(f"could not reach {url} after 3 attempts: timeout")

    monkeypatch.setattr(cu, "_get", fake_get)
    assert cu.main() == cu.EXIT_UNREACHABLE
    err = capsys.readouterr().err
    assert "UNREACHABLE" in err
    assert "not a finding" in err


def test_a_broken_probe_control_reports_its_own_results_meaningless(monkeypatch, capsys):
    base = _snapshot_matching_responses()

    def fake_get(url: str):
        if "definitely-not-a-real-thing" in url:
            return 401, b""          # control no longer discriminates
        return base(url)

    monkeypatch.setattr(cu, "_get", fake_get)
    assert cu.main() == cu.EXIT_DRIFT
    assert "meaningless" in capsys.readouterr().err


def test_get_retries_transient_failures_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class Boom(Exception):
        pass

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Boom("handshake timed out")
        raise AssertionError("should not reach a real request")

    monkeypatch.setattr(cu.time, "sleep", lambda *_: None)
    monkeypatch.setattr(cu.urllib.request, "urlopen", flaky)
    with pytest.raises(cu.Unreachable):
        cu._get("https://api.skilljar.com/v2/courses/")
    assert calls["n"] == cu.RETRIES, "must retry transient failures, not give up at one"
