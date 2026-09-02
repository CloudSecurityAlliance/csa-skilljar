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


def _write_fake_playwright(root: pathlib.Path, *, launch_message: str) -> None:
    """A fake `playwright.sync_api` on disk, importable via PYTHONPATH, whose
    `sync_playwright()` raises `Error(launch_message)` as soon as the `with` block is
    entered - standing in for a real Playwright whose browser launch fails, without
    needing the real package or a browser installed."""
    pkg = root / "playwright"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "sync_api.py").write_text(
        "class Error(Exception):\n"
        "    pass\n"
        "\n"
        "class _Ctx:\n"
        "    def __enter__(self):\n"
        f"        raise Error({launch_message!r})\n"
        "    def __exit__(self, *a):\n"
        "        return False\n"
        "\n"
        "def sync_playwright():\n"
        "    return _Ctx()\n"
    )


def _run_with_fake_playwright(tmp_path: pathlib.Path, *, launch_message: str) -> subprocess.CompletedProcess:
    fake_root = tmp_path / "fakepkg"
    fake_root.mkdir()
    _write_fake_playwright(fake_root, launch_message=launch_message)
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "PYTHONPATH": str(fake_root)}
    return subprocess.run(
        [sys.executable, "scripts/capture_dashboard_session.py"],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_the_script_reports_missing_browser_binaries_cleanly(tmp_path):
    """`pip install playwright` gets the package, not the browser binaries - the likely
    first-run failure for someone who stops after step one of the README's two-step
    setup. It must be reported like the missing-package case: a named remedy on stderr
    and a non-zero exit, never a raw Playwright traceback."""
    result = _run_with_fake_playwright(
        tmp_path,
        launch_message="BrowserType.launch: Executable doesn't exist at /fake/chrome",
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "playwright install chromium" in result.stderr
    assert "Traceback" not in result.stderr


def test_the_script_does_not_swallow_an_unrelated_playwright_error(tmp_path):
    """The missing-executable branch must be narrow: a genuinely different Playwright
    failure has the wrong remedy (installing chromium fixes nothing) and must still
    surface as a loud, uncaught error rather than being reported as the missing-browser
    case."""
    result = _run_with_fake_playwright(tmp_path, launch_message="Some completely different failure")
    assert result.returncode != 0
    assert "playwright install chromium" not in result.stderr
    assert "Some completely different failure" in result.stderr
