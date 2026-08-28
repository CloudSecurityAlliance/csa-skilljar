#!/usr/bin/env python3
"""Refuse to publish a distribution that carries something it should not.

Lived inside `release.yml` as a heredoc until 2026-08-28, which meant it ran exactly
once per release and was never tested. Its first real firing was a FALSE POSITIVE that
blocked v0.9.0: the rule matched the substring "credential" against every filename, so
`_tools/credentials.py` - a module named after the domain it implements - looked like a
credential file.

Two lessons, both applied here:

  * Match what a file IS, not what it is called. A credential arrives as a `.env`, a
    `.pem`, a `client_secret.json` - not as a Python module whose subject is credentials.
  * A guard that only runs at release time is a guard nobody can exercise. This is a
    script so `scripts/verify.sh` runs it and `tests/test_artifact_guard.py` can feed it
    deliberately bad archives.

Usage:  python scripts/check_artifact.py dist/*.whl dist/*.tar.gz
"""
from __future__ import annotations

import fnmatch
import pathlib
import sys
import tarfile
import zipfile

# Credential-shaped FILENAMES, matched against the basename. Deliberately specific:
# every entry names a way a secret actually reaches a repository, and none of them is a
# substring that legitimate source could contain.
SECRET_FILE_PATTERNS = (
    ".env", ".env.*", "*.env",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "id_rsa", "id_ed25519", "*.ppk",
    "client_secret*", "client_secrets*",
    "credentials.json", "credentials.yaml", "credentials.yml",
    "token.json", "tokens.json", "*.token",
    "service-account*.json", "*.netrc", ".npmrc", ".pypirc",
    "secrets.*",
)

# Directories that are repository furniture, not package content. Their absence is what
# keeps the wheel small and stops probe output shipping to PyPI.
EXCLUDED_PREFIXES = ("analysis/", "docs-html/", ".github/", ".venv/")

REQUIRED_SUFFIXES = ("py.typed",)


def entries(path: pathlib.Path) -> list[str]:
    if path.suffix == ".whl" or path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            return z.namelist()
    if path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path) as t:
            return t.getnames()
    raise ValueError(f"not a distribution this script understands: {path}")


def offending(names: list[str]) -> list[str]:
    """Names that must not ship. Basename for secrets, path prefix for directories."""
    bad = []
    for name in names:
        base = name.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(base.lower(), pat) for pat in SECRET_FILE_PATTERNS):
            bad.append(name)
            continue
        # An sdist prefixes everything with `pkg-version/`, so compare after that.
        tail = name.split("/", 1)[1] if "/" in name and not name.startswith(".") else name
        if any(tail.startswith(p) or name.startswith(p) for p in EXCLUDED_PREFIXES):
            bad.append(name)
    return sorted(set(bad))


def check(paths: list[pathlib.Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        names = entries(path)
        if not names:
            problems.append(f"{path.name}: archive is empty")
            continue
        bad = offending(names)
        if bad:
            problems.append(f"{path.name}: must not ship {bad}")
        for suffix in REQUIRED_SUFFIXES:
            # Only a wheel is required to carry py.typed at an importable location; an
            # sdist carries it too, but through the source tree.
            if not any(n.endswith(suffix) for n in names):
                problems.append(f"{path.name}: {suffix} is missing")
        print(f"  {path.name}: {len(names)} entries")
    return problems


def main(argv: list[str]) -> int:
    paths = [pathlib.Path(a) for a in argv]
    paths = [p for p in paths if p.exists()]
    if not paths:
        print("no distributions found to check - did the build run?", file=sys.stderr)
        return 1
    print(f"checking {len(paths)} distribution(s)")
    problems = check(paths)
    if problems:
        print("\nREFUSING TO PUBLISH:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("artifact contents clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
