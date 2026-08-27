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

# ZD-17: "no failures" and "the tests ran" are two facts. An all-skipped run reports
# 0 failures, and did once - a subdirectory conftest skipped the entire suite while
# every gate still said OK.
run_tests() {
  $PY -m pytest -q --no-header | tee /tmp/csa-skilljar-tests.$$
  local rc=${PIPESTATUS[0]}
  local passed
  passed=$(grep -oE '[0-9]+ passed' /tmp/csa-skilljar-tests.$$ | head -1 | grep -oE '[0-9]+')
  rm -f /tmp/csa-skilljar-tests.$$
  [ "$rc" -ne 0 ] && return 1
  if [ -z "${passed:-}" ] || [ "$passed" -lt 100 ]; then
    printf '   \033[31monly %s tests passed - expected 100+. Did something skip the suite?\033[0m\n' "${passed:-0}"
    return 1
  fi
  return 0
}

# CI runs bandit and pip-audit in a `security` job. They were absent here, so this
# script passed while CI failed - a local gate that is weaker than the remote one is
# worse than no local gate, because it teaches you to trust it.
security() {
  [ -x .venv/bin/bandit ] || { echo "!! bandit missing - .venv/bin/python -m pip install -e '.[dev]'"; return 1; }
  .venv/bin/bandit -q -r src && .venv/bin/pip-audit --progress-spinner off
}

step "tests"        run_tests
step "lint"         .venv/bin/ruff check src tests scripts
step "types"        .venv/bin/mypy
step "security"     security
step "doc claims"   $PY scripts/check_docs.py

printf '\n'
if [ "$fail" -ne 0 ]; then printf '\033[31mVERIFY FAILED - do not commit\033[0m\n'; exit 1; fi
printf '\033[32mverify passed\033[0m\n'
