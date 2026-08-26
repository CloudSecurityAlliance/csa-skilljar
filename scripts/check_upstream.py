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
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://api.skilljar.com"
TIMEOUT = 30

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
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310 - fixed https host
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"could not reach {url}: {e}") from e


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


def check_official_registry(drift: list[str]) -> bool:
    """The ADR-006 parity baseline. Returns False when it could not run.

    Reading it needs an interactive OAuth login (FRICTION-001), so this cannot run
    unattended today. Reported as skipped rather than passed.
    """
    return False


def main() -> int:
    print("checking Skilljar upstream against the snapshots in specs/\n")
    drift: list[str] = []
    check_v2_surface(drift)
    check_scope_catalogue(drift)
    check_reserved_areas(drift)
    ran_registry = check_official_registry(drift)

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
        return 1
    print("no drift: live Skilljar matches the snapshots in specs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
