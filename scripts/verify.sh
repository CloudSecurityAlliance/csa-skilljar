#!/usr/bin/env bash
# Everything CI will check, locally, with output you cannot miss.
#
# Written because failures were twice hidden by `cmd >/dev/null && echo ok` chains
# during Block 1 - a suppressed failure looks exactly like a pass. Run this before
# every commit. It never suppresses output and it fails loudly.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || { echo "!! no .venv - run: python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'"; exit 1; }

fail=0
step() {
  printf '\n\033[1m== %s\033[0m\n' "$1"; shift
  if "$@"; then printf '   \033[32mOK\033[0m\n'; else printf '   \033[31mFAILED\033[0m\n'; fail=1; fi
}

step "tests"        $PY -m pytest -q
step "lint"         .venv/bin/ruff check src tests scripts
step "types"        .venv/bin/mypy
step "doc claims"   $PY scripts/check_docs.py

printf '\n'
if [ "$fail" -ne 0 ]; then printf '\033[31mVERIFY FAILED - do not commit\033[0m\n'; exit 1; fi
printf '\033[32mverify passed\033[0m\n'
