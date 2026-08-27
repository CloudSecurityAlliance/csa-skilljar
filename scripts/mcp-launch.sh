#!/usr/bin/env bash
# Launch the MCP server with credentials read from a .env file at start-up.
#
# Why this exists: `claude mcp add -e KEY=value` writes the literal secret into
# ~/.claude.json, which is not gitignored and is not a secrets store, and puts it in
# your shell history on the way. Pointing the MCP client at this script instead keeps
# every credential in .env, which IS gitignored, and leaves the client configuration
# with no secret in it at all.
#
#   claude mcp add csa-skilljar -- /abs/path/to/scripts/mcp-launch.sh
#
# CSA_SKILLJAR_ENV_FILE overrides which file is read. Anything already exported in the
# environment WINS over the file, so a one-off override does not need the file edited.
#
# NOTHING may be written to stdout: under stdio, stdout is the JSON-RPC channel and one
# stray byte corrupts the session. Every diagnostic here goes to stderr.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
env_file="${CSA_SKILLJAR_ENV_FILE:-$repo/.env}"
server="$repo/.venv/bin/csa-skilljar-mcp"

if [ ! -x "$server" ]; then
  echo "csa-skilljar: no server at $server" >&2
  echo "  create the venv:  python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 1
fi

if [ -f "$env_file" ]; then
  # Read line by line rather than sourcing: `source` executes the file, so a stray
  # `echo` in .env would print to STDOUT and corrupt the protocol stream, and any other
  # command in it would simply run. This only ever assigns variables.
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"          # strip leading whitespace
    case "$line" in ''|'#'*) continue ;; esac
    line="${line#export }"
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      *[!A-Za-z0-9_]*|'') continue ;;                # not a shell-safe name; skip
      CSA_SKILLJAR_*) ;;                             # only ours - .env may hold others
      *) continue ;;
    esac
    # Strip one layer of matching quotes.
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    # Already exported wins, so an override does not need the file edited.
    if [ -z "${!key:-}" ]; then export "$key=$value"; fi
  done < "$env_file"
else
  echo "csa-skilljar: no env file at $env_file - starting without credentials." >&2
  echo "  Tools will report their setup steps; call check_access for details." >&2
fi

exec "$server" "$@"
