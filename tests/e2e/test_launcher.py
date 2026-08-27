"""`scripts/mcp-launch.sh` — reading credentials from a file instead of the MCP config.

`claude mcp add -e KEY=value` writes the literal secret into ~/.claude.json, which is
not gitignored and is not a secrets store. Pointing the client at this script keeps
credentials in .env and leaves the client configuration with no secret in it.

The script runs as PID 1 of the stdio session, so it is subject to invariant 1 as much
as the server is: anything it writes to stdout corrupts the JSON-RPC stream.
"""
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
LAUNCHER = ROOT / "scripts" / "mcp-launch.sh"

pytestmark = pytest.mark.skipif(
    not LAUNCHER.exists() or not (ROOT / ".venv" / "bin" / "csa-skilljar-mcp").exists(),
    reason="needs the launcher and a venv install")


def handshake(env_file, extra_env=None):
    """Start via the launcher, complete initialize, return (result, stdout, stderr)."""
    env = {"PATH": "/usr/bin:/bin", "CSA_SKILLJAR_ENV_FILE": str(env_file),
           **(extra_env or {})}
    p = subprocess.Popen([str(LAUNCHER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
    p.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
    p.stdin.flush()
    first = p.stdout.readline()
    p.stdin.close()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.terminate(); p.wait(timeout=10)
    return first, first + p.stdout.read(), p.stderr.read()


def test_a_stray_echo_in_the_env_file_cannot_reach_stdout(tmp_path):
    """THE reason this script reads line by line instead of `source`-ing.

    `source` EXECUTES the file. An `echo` in .env - a stray debug line, a pasted
    comment, anything - would print to stdout and corrupt the protocol stream before the
    server ever starts. Worse, any other command in it would simply run.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        'echo "THIS MUST NOT REACH STDOUT"\n'
        'CSA_SKILLJAR_PROFILE="parity"\n')
    first, stdout, _ = handshake(env_file)
    assert "THIS MUST NOT REACH STDOUT" not in stdout
    for line in stdout.splitlines():
        if line.strip():
            assert json.loads(line)["jsonrpc"] == "2.0"
    assert json.loads(first)["result"]["serverInfo"]["name"] == "csa-skilljar"


def test_a_command_in_the_env_file_is_not_executed(tmp_path):
    """`source` would run this. Reading assignments cannot."""
    marker = tmp_path / "executed"
    env_file = tmp_path / ".env"
    env_file.write_text(f'touch "{marker}"\nCSA_SKILLJAR_PROFILE=parity\n')
    handshake(env_file)
    assert not marker.exists(), "the launcher executed a command from the env file"


def test_values_from_the_file_reach_the_server(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('CSA_SKILLJAR_PROFILE="authoring"\n')
    first, _, _ = handshake(env_file)
    assert json.loads(first)["result"]["serverInfo"]["name"] == "csa-skilljar"
    # The profile is observable through check_access; asserting the handshake alone
    # would not prove the value was read, so read it back.
    p = subprocess.Popen(
        [str(LAUNCHER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
        env={"PATH": "/usr/bin:/bin", "CSA_SKILLJAR_ENV_FILE": str(env_file)})
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "check_access", "arguments": {}}}) + "\n")
    p.stdin.flush()
    p.stdout.readline()                                   # initialize
    payload = json.loads(json.loads(p.stdout.readline())["result"]["content"][0]["text"])
    p.stdin.close(); p.terminate(); p.wait(timeout=10)
    assert payload["profile"] == "authoring"


def test_an_exported_variable_beats_the_file(tmp_path):
    """So a one-off override does not need the credential file edited."""
    env_file = tmp_path / ".env"
    env_file.write_text('CSA_SKILLJAR_PROFILE=parity\n')
    p = subprocess.Popen(
        [str(LAUNCHER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
        env={"PATH": "/usr/bin:/bin", "CSA_SKILLJAR_ENV_FILE": str(env_file),
             "CSA_SKILLJAR_PROFILE": "reporting"})
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "check_access", "arguments": {}}}) + "\n")
    p.stdin.flush()
    p.stdout.readline()
    payload = json.loads(json.loads(p.stdout.readline())["result"]["content"][0]["text"])
    p.stdin.close(); p.terminate(); p.wait(timeout=10)
    assert payload["profile"] == "reporting"


def test_only_our_own_variables_are_exported(tmp_path):
    """The real .env in this repo also holds a v1 testing key that is not ours to
    export. Reading a credential file must not scatter everything in it into the
    server's environment."""
    env_file = tmp_path / ".env"
    env_file.write_text('SOME_OTHER_SECRET=leaked\nCSA_SKILLJAR_PROFILE=parity\n')
    out = subprocess.run(
        ["/bin/bash", "-c",
         f'CSA_SKILLJAR_ENV_FILE={env_file} '
         f'{LAUNCHER} --version >/dev/null 2>&1; env | grep -c SOME_OTHER_SECRET || true'],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert out.stdout.strip() == "0"


def test_a_missing_env_file_warns_on_stderr_and_still_starts(tmp_path):
    """The server is designed to start with no credentials at all; the launcher must not
    take that away."""
    first, stdout, stderr = handshake(tmp_path / "nope.env")
    assert json.loads(first)["result"]["serverInfo"]["name"] == "csa-skilljar"
    assert "no env file" in stderr
    for line in stdout.splitlines():
        if line.strip():
            assert json.loads(line)["jsonrpc"] == "2.0"


def test_the_launcher_never_prints_a_value_it_read(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('CSA_SKILLJAR_V2_CLIENT_SECRET="sk-live-DEADBEEF-do-not-print"\n')
    _, stdout, stderr = handshake(env_file)
    assert "DEADBEEF" not in stdout
    assert "DEADBEEF" not in stderr
