#!/usr/bin/env python3
"""Assert every factual claim in this repo's documentation against the artifacts.

We have far more prose than code right now, and prose about unbuilt software rots
silently. This makes the numbers load-bearing: if a doc says the v2 API has 82
operations, that is checked against `specs/skilljar-v2-openapi.json`, not trusted.

Run:  python scripts/check_docs.py
Exit: 0 all claims hold · 1 a claim disagrees with an artifact

This is deliberately about *internal* consistency - docs versus the snapshots we
hold. `scripts/check_upstream.py` is the separate question of whether the snapshots
still match live Skilljar.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _spec_counts(path: pathlib.Path) -> tuple[int, int]:
    """(paths, operations) for an OpenAPI document.

    JSON only, deliberately. `specs/skilljar-v1-openapi.json` exists precisely so tooling
    does not need a YAML parser, and requiring PyYAML here would add a dependency to a
    script whose whole job is to run anywhere with nothing installed. The YAML remains the
    as-fetched artifact; `check_upstream.py` is what notices if it drifts from upstream.
    """
    spec = json.loads(path.read_text())
    verbs = ("get", "post", "put", "patch", "delete")
    ops = sum(1 for item in spec["paths"].values() for m in item if m in verbs)
    return len(spec["paths"]), ops


def _v2_scopes_used() -> int:
    spec = json.loads((ROOT / "specs" / "skilljar-v2-openapi.json").read_text())
    flat: set[str] = set()
    for item in spec["paths"].values():
        for method, op in item.items():
            if method not in ("get", "post", "put", "patch", "delete"): continue
            if not isinstance(op, dict): continue
            raw = op.get("x-required-scope")
            if not raw: continue
            for entry in ([raw] if isinstance(raw, str) else raw):
                flat.update(s.strip() for s in entry.split(",") if s.strip())
    return len(flat)


def _captured_tool_count() -> int:
    n = 0
    for f in (ROOT / "specs" / "official-mcp").glob("registry-*.json"):
        d = json.loads(f.read_text())
        for key in ("tools", "get_tools", "delete_tools"):
            n += len([k for k in d.get(key, {}) if not k.startswith("_")])
    return n


def _roadmap_parity_tool_sum() -> int:
    """Blocks 2-9 are the parity blocks; their headings carry '· N tools'."""
    text = (ROOT / "ROADMAP.md").read_text()
    total = 0
    for m in re.finditer(r"^### Block (\d+) — .*?· (\d+) tools", text, re.M):
        if 2 <= int(m.group(1)) <= 9: total += int(m.group(2))
    return total


def build_checks() -> list[tuple[str, int, list[tuple[str, str]]]]:
    """(label, truth, [(relative_path, regex with one capturing group)]).

    Patterns are matched against the real prose. When a doc is reworded and a pattern
    stops matching, that is a FAILURE, not a silent pass - a claim we can no longer
    locate is a claim we can no longer verify.
    """
    v1_paths, v1_ops = _spec_counts(ROOT / "specs" / "skilljar-v1-openapi.json")
    v2_paths, v2_ops = _spec_counts(ROOT / "specs" / "skilljar-v2-openapi.json")
    scopes_advertised = len(json.loads(
        (ROOT / "analysis" / "live-authz-metadata.json").read_text())["scopes_supported"])
    entities = len(json.loads((ROOT / "analysis" / "entity-inventory.json").read_text()))
    tools = len(json.loads((ROOT / "specs" / "official-mcp" / "tool-names.json").read_text()))

    S = "docs/superpowers/specs/2026-08-26-csa-skilljar-design.md"
    return [
        ("v1 operations", v1_ops, [
            (S, r"\((\d+) operations against v2's \d+\)"),
            (S, r"160 paths / (\d+) ops"),
            ("README.md", r"(\d+) operations against v2's"),
        ]),
        ("v1 paths", v1_paths, [(S, r"OpenAPI 3\.0\.3, (\d+) paths")]),
        ("v2 operations", v2_ops, [
            (S, r"operations against v2's (\d+)\)"),
            (S, r"44 paths / (\d+) ops"),
            ("README.md", r"operations against v2's (\d+)"),
        ]),
        ("v2 paths", v2_paths, [(S, r"OpenAPI 3\.1\.0, (\d+) paths")]),
        ("official MCP tools", tools, [
            (S, r"exposes \*\*(\d+) tools\*\*"),
            ("README.md", r"v2 API in (\d+)"),
            ("README.md", r"Reproduces all (\d+) official tools"),
            ("ROADMAP.md", r"completing parity \((\d+) tools\)"),
            ("specs/official-mcp/README.md", r"All \*\*(\d+) tools\*\*"),
        ]),
        ("scopes advertised", scopes_advertised, [
            (S, r"advertises \*\*(\d+) OAuth scopes\*\*"),
            (S, r"Scope catalog \| (\d+) advertised"),
            ("README.md", r"advertises \*\*(\d+) scopes\*\*"),
            ("CLAUDE.md", r"advertises\s+\*\*(\d+) scopes\*\*"),
        ]),
        ("scopes used by the v2 spec", _v2_scopes_used(), [
            (S, r"published v2 spec uses \*\*(\d+)\*\*"),
            (S, r"(\d+) used by the published spec"),
            ("README.md", r"uses \*\*(\d+)\*\*"),
            ("CLAUDE.md", r"uses\s+\*\*(\d+)\*\*"),
        ]),
        ("entities in the inventory", entities, [
            ("CLAUDE.md", r"(\d+)-entity"),
            ("CHANGELOG.md", r"(\d+)-entity"),
        ]),
    ]


def main() -> int:
    failures: list[str] = []
    checked = 0

    for label, truth, sites in build_checks():
        for rel, pattern in sites:
            path = ROOT / rel
            if not path.exists():
                failures.append(f"{label}: {rel} does not exist"); continue
            found = re.findall(pattern, path.read_text(), re.S)
            if not found:
                failures.append(f"{label}: pattern {pattern!r} matched nothing in {rel}")
                continue
            for got in found:
                checked += 1
                if int(got) != truth:
                    failures.append(f"{label}: {rel} says {got}, artifacts say {truth}")

    # Cross-artifact invariants - not a doc claim, a consistency requirement.
    tools = len(json.loads((ROOT / "specs" / "official-mcp" / "tool-names.json").read_text()))
    captured = _captured_tool_count(); checked += 1
    if captured != tools:
        failures.append(f"captured registry holds {captured} tools, tool-names.json holds {tools}")

    parity = _roadmap_parity_tool_sum(); checked += 1
    if parity != tools:
        failures.append(f"ROADMAP parity blocks 2-9 sum to {parity} tools, official registry has {tools}")

    print(f"checked {checked} claims across the documentation")
    if failures:
        print("\nFAILED:", file=sys.stderr)
        for f in failures: print(f"  - {f}", file=sys.stderr)
        return 1
    print("all claims agree with the artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
