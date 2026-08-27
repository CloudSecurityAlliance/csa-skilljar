#!/usr/bin/env python3
"""Detect drift between live Skilljar and the snapshots in `specs/`.

This project's whole premise has a shelf life. Skilljar has publicly reserved OAuth
scopes for webhooks, paths, assets, tags and commerce - the capabilities this project
exists to reach - so every gap it fills is on someone else's roadmap. Noticing when one
closes is what makes retirement evidence-driven rather than something somebody
remembers to check.

Four checks, cheapest first:

1. v2 surface        - paths and operations vs specs/skilljar-v2-openapi.json
2. scope catalogue   - advertised scopes vs analysis/live-authz-metadata.json
3. reserved areas    - 401-vs-404 per undocumented scope area (the WAITING-FOR-001 trigger)
4. official registry - the ADR-006 parity baseline, only with credentials

Run:  .venv/bin/python scripts/check_upstream.py
Exit: 0 no drift · 1 drift detected · 2 could not reach Skilljar

ZD-17, silence is not health: a check that could not run is reported as SKIPPED, never
folded into a pass. "No drift" and "the check ran" are two separate facts and both are
printed.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://api.skilljar.com"
TIMEOUT = 30
RETRIES = 3
BACKOFF_SECONDS = 2.0

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNREACHABLE = 2


class Unreachable(Exception):
    """Skilljar could not be reached. An infrastructure problem, NOT a finding.

    Kept distinct from drift because conflating them is the ZD-17 failure in reverse:
    the first scheduled run failed on a single transient SSL handshake timeout among 34
    sequential probes, and reported identically to real drift. An outage that looks like
    a finding trains people to ignore findings.
    """

# Scope areas advertised by the authorization server that had no endpoint on 2026-08-26.
# Each is a v1 family this project currently carries; a 401 here is the signal to plan
# its retirement. See WAITING-FOR-001.
RESERVED_AREAS = [
    "webhooks", "paths", "assets", "labels", "tags", "themes", "content-items",
    "instructors", "course-families", "catalog-pages", "plans", "email-templates",
    "language-packs", "admin-users", "roles", "audit", "promo-codes",
    "training-credits", "licensing", "offers", "orders", "access-codes",
    "vilt-sessions", "scheduled-reports", "data-export", "workflows", "syndication",
    "announcements", "action-items", "organization", "integrations",
]


def _get(url: str) -> tuple[int, bytes]:
    """GET with retries. An HTTP status - including 401/404 - is a RESULT, not a failure.

    Only a transport-level failure is retried, and only a persistent one raises.
    """
    last: Exception | None = None
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https host
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""          # a status we asked for; never retried
        except Exception as e:          # noqa: BLE001 - URLError, TimeoutError, ssl errors
            last = e
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise Unreachable(f"could not reach {url} after {RETRIES} attempts: {last}")


def check_v2_surface(drift: list[str]) -> None:
    snapshot = json.loads((ROOT / "specs" / "skilljar-v2-openapi.json").read_text())
    status, body = _get(f"{BASE}/v2/openapi.json")
    if status != 200:
        drift.append(f"v2 spec fetch returned HTTP {status}")
        return
    live = json.loads(body)
    old, new = set(snapshot["paths"]), set(live["paths"])
    print(f"  v2 surface: {len(new)} paths live, {len(old)} in snapshot")
    for p in sorted(new - old):
        drift.append(f"NEW v2 path: {p}")
    for p in sorted(old - new):
        drift.append(f"REMOVED v2 path: {p}")


def check_scope_catalogue(drift: list[str]) -> None:
    snapshot = set(json.loads(
        (ROOT / "analysis" / "live-authz-metadata.json").read_text())["scopes_supported"])
    status, body = _get(f"{BASE}/.well-known/oauth-authorization-server")
    if status != 200:
        drift.append(f"authorization-server metadata returned HTTP {status}")
        return
    live = set(json.loads(body).get("scopes_supported", []))
    print(f"  scope catalogue: {len(live)} advertised, {len(snapshot)} in snapshot")
    for s in sorted(live - snapshot):
        drift.append(f"NEW advertised scope: {s}")
    for s in sorted(snapshot - live):
        drift.append(f"WITHDRAWN scope: {s}")


def check_reserved_areas(drift: list[str]) -> None:
    """The retirement trigger. 404 = still unbuilt; anything else = it exists now.

    The control matters: /v2/courses/ must 401 and a nonsense path must 404, or the
    probe is not discriminating and its result means nothing.
    """
    control_real, _ = _get(f"{BASE}/v2/courses/")
    control_fake, _ = _get(f"{BASE}/v2/definitely-not-a-real-thing/")
    if not (control_real == 401 and control_fake == 404):
        drift.append(f"probe control failed: /v2/courses/={control_real} "
                     f"nonsense={control_fake}; 401-vs-404 no longer discriminates, "
                     f"so the reserved-area results below are meaningless")
        return
    shipped = []
    for area in RESERVED_AREAS:
        status, _ = _get(f"{BASE}/v2/{area}/")
        if status != 404:
            shipped.append(f"{area} (HTTP {status})")
    print(f"  reserved areas: {len(RESERVED_AREAS)} probed, {len(shipped)} now shipped")
    for s in shipped:
        drift.append(f"v2 SHIPPED a reserved area: {s} - see WAITING-FOR-001, "
                     f"the matching v1 family can now be retired")


def check_client_credentials_grant(drift: list[str]) -> None:
    """The single assumption the whole project rests on (ADR-003).

    If Skilljar ever stops accepting `client_credentials`, this server cannot
    authenticate at all - there is no browser here to run `authorization_code` through.
    That is a total failure, so it is worth a free probe on every drift check.

    The probe needs no credentials, because the two outcomes are distinguishable
    without one:

        401 invalid_client   the grant was ACCEPTED and reached the credential check
        400 invalid_request  the grant itself was rejected

    Deliberately fake credentials are sent. Nothing is created and nothing is logged in
    against.
    """
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": "csa-skilljar-upstream-probe-not-a-real-client",
        "client_secret": "not-a-real-secret",  # nosec B106 # a deliberate non-credential
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v2/auth/token", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https host
            status, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    except Exception as e:  # noqa: BLE001
        raise Unreachable(f"could not reach the token endpoint: {e}") from e

    try:
        error = json.loads(payload).get("error", "")
    except ValueError:
        error = ""
    print(f"  client_credentials grant: HTTP {status} {error or '(no error field)'}")

    if status == 401 and error == "invalid_client":
        return                              # accepted; only our fake credentials failed
    drift.append(
        f"client_credentials may no longer be accepted at {BASE}/v2/auth/token "
        f"(expected HTTP 401 invalid_client, got HTTP {status} {error!r}). "
        f"ADR-003 depends on this grant; without it this server cannot authenticate.")


def check_official_registry(drift: list[str]) -> bool:
    """The ADR-006 parity baseline. Returns False when it could not run.

    Reading it needs an interactive OAuth login (FRICTION-001), so this cannot run
    unattended today. Reported as skipped rather than passed.
    """
    return False


def main() -> int:
    print("checking Skilljar upstream against the snapshots in specs/\n")
    drift: list[str] = []
    try:
        check_v2_surface(drift)
        check_scope_catalogue(drift)
        check_reserved_areas(drift)
        check_client_credentials_grant(drift)
        ran_registry = check_official_registry(drift)
    except Unreachable as e:
        # NOT drift. Exit 2 so the caller can tell an outage from a finding.
        print(f"\nUNREACHABLE: {e}", file=sys.stderr)
        print("This is an infrastructure problem, not a finding about Skilljar's API. "
              "Nothing about the snapshots in specs/ has been established either way.",
              file=sys.stderr)
        return EXIT_UNREACHABLE

    print()
    if not ran_registry:
        print("  SKIPPED official MCP tool registry - reading it needs an interactive "
              "OAuth login (FRICTION-001).")
        print("           Compare by hand against specs/official-mcp/tool-names.json.")
    print()

    if drift:
        print(f"DRIFT DETECTED ({len(drift)} findings):", file=sys.stderr)
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        print("\nRefresh specs/ and analysis/, regenerate scopes.py, and update the "
              "coverage map.", file=sys.stderr)
        return EXIT_DRIFT
    print("no drift: live Skilljar matches the snapshots in specs/")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
