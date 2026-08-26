"""Console-script entry point.

    csa-skilljar-mcp             # run the stdio server, for an MCP client to launch
    csa-skilljar-mcp --version   # print the installed version and exit

Everything prints to stderr. stdout belongs to JSON-RPC, and a single stray byte on it
corrupts the session while leaving the server looking alive.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping, Sequence

from .. import __version__
from ._config import (
    V1_MISSING_WARNING,
    V2_MISSING_WARNING,
    ClientProvider,
    Settings,
    presence_from_env,
    settings_from_env,
)
from .server import create_server

USAGE = """usage: csa-skilljar-mcp [--version]

  (no argument)   run the MCP server over stdio, for an MCP client to launch
  --version       print the installed version and exit

environment:
  CSA_SKILLJAR_V2_CLIENT_ID      v2 OAuth client id
  CSA_SKILLJAR_V2_CLIENT_SECRET  v2 OAuth client secret
  CSA_SKILLJAR_V1_API_KEY        v1 organization API key (no v1 tools yet)
  CSA_SKILLJAR_PROFILE           parity (default) | authoring | people | reporting
                                 | operations | admin | full
"""


def _configure_logging() -> None:
    """Give the library's `logging` calls a destination, and make it stderr.

    Without this a warning from `decode_claims` goes nowhere and the diagnostic is lost.
    With a StreamHandler on stdout it would corrupt the JSON-RPC channel instead. Most
    MCP clients surface a server's stderr in their logs, which is the only place to say
    anything before the first tool call.
    """
    root = logging.getLogger("csa_skilljar")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("csa-skilljar: %(levelname)s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)


def _run_server(settings: Settings, provider: ClientProvider) -> None:
    """Seam so tests can stub the blocking call."""
    create_server(provider, settings=settings).run(transport="stdio")


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env

    if argv and argv[0] in ("-h", "--help", "help"):
        print(USAGE, file=sys.stderr); return 0
    if argv and argv[0] in ("-V", "--version", "version"):
        print(__version__, file=sys.stderr); return 0
    if argv:
        print(f"unknown argument: {argv[0]}\n\n{USAGE}", file=sys.stderr); return 2

    _configure_logging()
    settings = settings_from_env(env)
    # stderr, never stdout. Most MCP clients surface a server's stderr in their logs,
    # which is the only place to say this before the first tool call.
    # The printed strings are module CONSTANTS; the environment only decides *whether*
    # each is printed. So there is no data path from os.environ to this output at all,
    # only a control-flow one. See CredentialPresence and V2_MISSING_WARNING.
    presence = presence_from_env(env)
    if not presence.v2:
        print(f"csa-skilljar: {V2_MISSING_WARNING}", file=sys.stderr)
    if not presence.v1:
        print(f"csa-skilljar: {V1_MISSING_WARNING}", file=sys.stderr)

    # Credentials are never resolved here: a missing one must not stop the server
    # starting, or the client reports an opaque "server failed to start" and the user
    # never sees the remedy. Tools surface it instead, where it is readable.
    _run_server(settings, ClientProvider(settings))
    return 0
