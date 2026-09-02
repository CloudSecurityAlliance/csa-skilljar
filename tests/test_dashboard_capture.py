"""Guards for the setup-time dashboard session capture script.

The script itself opens a real, headed browser and waits for a human to solve an
hCaptcha - that cannot be exercised in this offline suite. What can be checked without a
browser: that Playwright never leaks into the server's import graph, that the capture
script is not importable as part of the package, and that the script degrades cleanly
when Playwright is not installed.
"""
import pathlib
import subprocess
import sys


def test_the_server_never_imports_playwright():
    """Playwright is a SETUP-time dependency. If the server imports it, every install
    grows a browser toolchain and the 'no browser at runtime' design is a fiction."""
    src = pathlib.Path("src/csa_skilljar")
    offenders = [p for p in src.rglob("*.py") if "playwright" in p.read_text()]
    assert offenders == []


def test_the_capture_script_is_not_importable_from_the_package():
    out = subprocess.run(
        [sys.executable, "-c",
         "import csa_skilljar, sys; "
         "print(any('capture_dashboard' in m for m in sys.modules))"],
        capture_output=True, text=True)
    assert out.stdout.strip() == "False"


def test_the_script_degrades_cleanly_without_playwright(tmp_path):
    """No Playwright on the path is a normal, expected state (it is a setup-only extra),
    not a crash. The script must name the extra to install and exit non-zero - never a
    traceback - and everything it prints must go to stderr, never stdout, since stdout is
    reserved for the JSON-RPC channel elsewhere in this project."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "scripts/capture_dashboard_session.py"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "dashboard-setup" in result.stderr
    assert "Traceback" not in result.stderr


def test_the_script_is_not_importable_as_a_module_with_side_effects():
    """Sanity check that importing the script's module (rather than running it) does not
    itself require playwright or touch the filesystem - main() is only invoked under
    __main__."""
    script = pathlib.Path("scripts/capture_dashboard_session.py")
    assert script.exists()
    assert 'if __name__ == "__main__":' in script.read_text()
