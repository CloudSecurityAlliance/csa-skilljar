"""Drive the installed console script over stdio, the way a real MCP client does.

Every other test in this repo builds the server in-process. That is fast and it is
where the behaviour lives, but it cannot see anything that only exists once there is a
subprocess: the initialize handshake, what the SDK puts on stdout, what the CLI writes
to stderr, or whether the console script is wired up at all.

Three real defects have hidden in exactly that gap - a `pipx install` that produced a
broken command, and an EMPTY `serverInfo.version` that every in-process test was blind
to because none of them reads the handshake.

No credentials are set. The server must still start: design spec section 5, and the
reason startup does not block on a network call.
"""
import json
import os
import subprocess
import sys

import pytest

import csa_skilljar

# Resolve the script NEXT TO the interpreter running the tests - never through PATH.
# `shutil.which` found a pipx install from an earlier release on the first run here and
# the suite happily tested it: eight tools missing, a stale version, and every assertion
# reporting on software that is not this checkout. An end-to-end test that can silently
# exercise a different build is worse than none.
SCRIPT = os.path.join(os.path.dirname(sys.executable), "csa-skilljar-mcp")

# NOT a skipif. Any editable or wheel install puts this script next to the
# interpreter, so its absence is a broken install, not a reason to go quiet - and a
# suite that skips itself reports green while testing nothing (ZD-17). Opting out is
# possible but has to be deliberate.
if not os.path.exists(SCRIPT):
    if os.environ.get("CSA_SKILLJAR_NO_E2E") == "1":
        pytest.skip("CSA_SKILLJAR_NO_E2E=1", allow_module_level=True)
    raise RuntimeError(
        f"csa-skilljar-mcp is not installed at {SCRIPT}. The end-to-end suite needs "
        f"the real console script. Run `pip install -e '.[dev]'` in this venv, or set "
        f"CSA_SKILLJAR_NO_E2E=1 to skip it deliberately.")


class Server:
    """A live server subprocess, spoken to in JSON-RPC over its stdin and stdout."""

    def __init__(self, env=None):
        # A DELIBERATELY BARE environment. Inheriting os.environ would let a developer's
        # real CSA_SKILLJAR_* credentials leak in and turn an offline test into one that
        # talks to production - and would hide the no-credential path this exists to
        # check.
        self.proc = subprocess.Popen(
            [SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env={"PATH": "/usr/bin:/bin", **(env or {})})
        self._id = 0
        # Every line stdout ever produced, so the teardown check sees the whole session
        # rather than only what was read in time.
        self.stdout_lines: list[str] = []

    def _send(self, payload):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def call(self, method, params=None):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params or {}})
        line = self.proc.stdout.readline()
        assert line.strip(), f"server produced no response to {method}"
        self.stdout_lines.append(line)
        message = json.loads(line)
        assert "error" not in message, f"{method} failed: {message['error']}"
        return message["result"]

    def notify(self, method):
        self._send({"jsonrpc": "2.0", "method": method})

    def handshake(self):
        result = self.call("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "e2e", "version": "0"}})
        self.notify("notifications/initialized")
        return result

    def close(self):
        """Shut down and return (stderr, every stdout line the session ever produced).

        Reading stdout only up to the last response is not enough. `print()` to a pipe
        is BLOCK-buffered, not line-buffered, so a stray write sits in the buffer until
        the process exits and lands after every response this test read. The first
        version of this file missed exactly that: a `print()` added to `main()` did not
        fail a single assertion. Whatever is still in the buffer at exit is part of what
        the client would have had to parse.
        """
        # Closing stdin asks the stdio loop to finish, and a GRACEFUL exit is what
        # flushes Python's block-buffered stdout. Going straight to terminate() sends
        # SIGTERM, which tears the process down WITHOUT flushing - so stray bytes
        # vanish in the test and appear in production. That is why the earlier version
        # of this file could not catch a `print()` in `main()`.
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.stdout_lines.extend(
            line for line in self.proc.stdout.read().splitlines() if line.strip())
        return self.proc.stderr.read(), self.stdout_lines


@pytest.fixture
def server():
    """Every test gets the stdout-purity check for free, at teardown.

    Invariant 1 is the one that fails silently and the one nobody remembers to assert,
    so it is not left to a single test to remember: whatever any test happened to
    exercise, the whole session's stdout must have been JSON-RPC and nothing else.
    """
    s = Server()
    yield s
    if s.proc.poll() is None or not s.stdout_lines:
        _, lines = s.close()
    else:
        lines = s.stdout_lines
    for line in lines:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:  # noqa: PERF203
            pytest.fail(
                "NON-JSON BYTES ON STDOUT. Under stdio, stdout IS the protocol "
                f"channel; this corrupts the session. Offending line: {line!r}")
        assert message.get("jsonrpc") == "2.0", (
            f"a JSON object that is not JSON-RPC reached stdout: {line!r}")


def test_the_script_under_test_is_this_checkout():
    """Guards every other test in this file. They are only meaningful if the subprocess
    is running the source in this repository - see the note on SCRIPT above."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import csa_skilljar, sys; sys.stdout.write(csa_skilljar.__file__)"],
        capture_output=True, text=True, check=True).stdout
    repo_src = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "src"))
    assert os.path.realpath(out).startswith(repo_src), (
        f"the interpreter imports csa_skilljar from {out}, not {repo_src}. "
        f"Run `pip install -e '.[dev]'` inside this repo's venv.")
    assert os.path.realpath(csa_skilljar.__file__).startswith(repo_src)


def test_the_server_starts_with_no_credentials_at_all(server):
    """The design's first promise. A server that refused to start without credentials
    would surface as an opaque "server failed to start" with no way to say why."""
    info = server.handshake()["serverInfo"]
    assert info["name"] == "csa-skilljar"


def test_the_handshake_reports_a_real_version(server):
    """It reported an EMPTY string until a stdio smoke test looked. serverInfo is what a
    client shows when someone asks which build they are talking to, and no in-process
    test reads it."""
    from csa_skilljar import __version__
    version = server.handshake()["serverInfo"]["version"]
    assert version, "serverInfo.version is empty - the client cannot identify the build"
    assert version == __version__


def test_every_registered_tool_is_published_over_the_wire(server):
    """In-process registration and what a client actually receives are two facts.

    Counted against the live registry rather than a literal: the number moved twice in
    one day, and a hardcoded one turns every new block into an edit here that teaches
    nothing."""
    from csa_skilljar.mcp._config import settings_from_env
    from csa_skilljar.mcp.server import create_server

    def unreachable():
        raise AssertionError("counting tools must not construct a client")

    expected = len(create_server(unreachable,
                                 settings=settings_from_env({}))._tool_manager._tools)
    server.handshake()
    tools = server.call("tools/list")["tools"]
    assert len(tools) == expected
    names = {t["name"] for t in tools}
    assert "list_courses" in names and "register_oauth_client" in names


def test_every_published_tool_has_a_description_and_a_schema(server):
    server.handshake()
    for tool in server.call("tools/list")["tools"]:
        assert tool.get("description"), f"{tool['name']} published with no description"
        assert tool["inputSchema"]["type"] == "object"


def test_check_access_works_without_credentials_and_names_the_remedy(server):
    """The tool whose entire job is to work when nothing else can."""
    server.handshake()
    result = server.call("tools/call", {"name": "check_access", "arguments": {}})
    payload = json.loads(result["content"][0]["text"])
    assert payload["v2"]["configured"] is False
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in payload["v2"]["detail"]


def test_an_uncredentialed_tool_call_explains_itself_rather_than_crashing(server):
    """The failure a first-time user actually hits. It must name the variables to set,
    not say "Error executing tool"."""
    server.handshake()
    result = server.call("tools/call",
                         {"name": "list_courses", "arguments": {}})
    text = result["content"][0]["text"]
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in text
    assert "check_access" in text


def test_nothing_but_json_rpc_reaches_stdout(server):
    """Invariant 1, and it fails silently: under stdio, stdout IS the protocol channel.
    One stray byte corrupts the session and the server looks alive while answering
    nothing. Every diagnostic must go to stderr."""
    server.handshake()
    server.call("tools/list")
    server.call("tools/call", {"name": "check_access", "arguments": {}})
    # Errors are the most likely thing to be printed carelessly, so provoke one.
    server.call("tools/call", {"name": "list_courses", "arguments": {}})
    stderr, stdout_lines = server.close()
    # The diagnostics went to stderr...
    assert "CSA_SKILLJAR_V2_CLIENT_ID" in stderr
    # ...and every byte of stdout, INCLUDING whatever was flushed at exit, was
    # JSON-RPC. The fixture asserts this too; stating it here is what makes this test
    # about the invariant rather than about the calls.
    assert stdout_lines, "no stdout captured - this test would prove nothing"
    for line in stdout_lines:
        assert json.loads(line)["jsonrpc"] == "2.0"


def test_the_startup_warning_goes_to_stderr_not_stdout(server):
    server.handshake()
    stderr, _ = server.close()
    assert "not set" in stderr
