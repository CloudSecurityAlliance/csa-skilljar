import contextlib
import io
import sys

import csa_skilljar
from csa_skilljar.mcp.cli import main


def run(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, env=env or {})
    return code, out.getvalue(), err.getvalue()


def test_version_prints_to_stderr_and_exits_zero():
    """An installer must be able to check what it just installed without starting a
    session. A pipx upgrade that silently changed nothing must not look like one that
    worked."""
    code, out, err = run(["--version"])
    assert code == 0
    assert out == ""
    assert csa_skilljar.__version__ in err


def test_help_goes_to_stderr():
    code, out, err = run(["--help"])
    assert code == 0
    assert out == ""
    assert "usage" in err.lower()


def test_unknown_argument_is_an_error_with_usage():
    code, out, err = run(["--wat"])
    assert code == 2
    assert out == ""
    assert "usage" in err.lower()


def test_startup_warnings_reach_stderr_when_credentials_are_absent(monkeypatch):
    import csa_skilljar.mcp.cli as cli
    monkeypatch.setattr(cli, "_run_server", lambda *a, **k: None)
    code, out, err = run([], env={})
    assert out == ""
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in err


def test_logging_is_routed_to_stderr_never_stdout(monkeypatch):
    """The library reports through `logging`; the CLI is what gives it a destination.

    Asserted on the handler rather than by capturing output: a StreamHandler binds its
    stream at construction, so `redirect_stderr` afterwards does not move it. That is
    correct for a real server (nothing swaps sys.stderr under it) and it means the
    property to test is *which stream the handler holds*, not what a redirect sees.
    """
    import logging

    import csa_skilljar.mcp.cli as cli
    monkeypatch.setattr(cli, "_run_server", lambda *a, **k: None)
    logging.getLogger("csa_skilljar").handlers.clear()

    main([], env={})

    handlers = logging.getLogger("csa_skilljar").handlers
    assert handlers, "the CLI must give the library's logging a destination"
    for h in handlers:
        stream = getattr(h, "stream", None)
        assert stream is not sys.stdout, "stdout is the JSON-RPC channel"
        assert stream is sys.stderr


def test_configuring_logging_twice_does_not_duplicate_handlers(monkeypatch):
    import logging

    import csa_skilljar.mcp.cli as cli
    monkeypatch.setattr(cli, "_run_server", lambda *a, **k: None)
    logging.getLogger("csa_skilljar").handlers.clear()
    main([], env={}); main([], env={})
    assert len(logging.getLogger("csa_skilljar").handlers) == 1
