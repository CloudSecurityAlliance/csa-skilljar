#!/usr/bin/env python3
"""Capture a Skilljar dashboard session for the MCP server to reuse.

The dashboard login is protected by hCaptcha. We do not attempt to defeat it - a human
solves it, which is what it is for. This script opens a real, headed browser, waits for
you to log in, and saves the resulting cookies.

    .venv/bin/python scripts/capture_dashboard_session.py

Requires the setup extra:  pip install -e ".[dashboard-setup]" && playwright install chromium

Playwright is a SETUP-time dependency only - the MCP server itself never imports it. This
script is not part of the `csa_skilljar` package and is never imported by it.
"""
from __future__ import annotations

import os
import pathlib
import sys

OUT = pathlib.Path.home() / ".csa_skilljar" / "dashboard-session.json"
LOGIN = "https://dashboard.skilljar.com/login"

_MISSING_EXECUTABLE = "Executable doesn't exist"


def main() -> int:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            'playwright is not installed. Run: pip install -e ".[dashboard-setup]" '
            "&& playwright install chromium",
            file=sys.stderr,
        )
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(OUT.parent, 0o700)

    # `pip install` gets the playwright PACKAGE; it does not download browser binaries.
    # That is the likely first-run failure - a person who stops after step one of the
    # README's two-step setup hits it every time - so it gets the same clean-message
    # treatment as playwright being absent entirely, not a raw traceback. Anything else
    # from launch/login is a genuine surprise and must still surface.
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # headed: a human must log in
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(LOGIN)
            print("A browser has opened. Log in to the Skilljar dashboard.", file=sys.stderr)
            print("This window will close once you reach the dashboard.", file=sys.stderr)
            try:
                page.wait_for_url(lambda u: "/login" not in u, timeout=300_000)
            except Exception:
                print("timed out waiting for login; nothing was saved", file=sys.stderr)
                browser.close()
                return 1
            # Write 0600 from creation, not chmod afterwards - there must be no window in
            # which a live admin session cookie is world-readable.
            fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)
            ctx.storage_state(path=str(OUT))
            os.chmod(OUT, 0o600)
            browser.close()
    except PlaywrightError as e:
        if _MISSING_EXECUTABLE not in str(e):
            raise
        print(
            "playwright's browser is not installed. Run: playwright install chromium",
            file=sys.stderr,
        )
        return 2

    print(f"session saved to {OUT} (0600)", file=sys.stderr)
    print(f"Now set:  CSA_SKILLJAR_DASHBOARD_SESSION={OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
