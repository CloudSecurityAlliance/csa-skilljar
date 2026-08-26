"""`report_a_problem` - the feedback path, and the answer to "how do I report this?".

Assembles version, platform and active policy into something filable. Contains no ids
and no credentials by design, so what actually happened stays the user's to describe.
"""
from __future__ import annotations

import platform
import sys

from mcp.server import MCPServer

from ... import __version__
from .._config import Settings
from .._schemas import ProblemReportOut
from ._base import READ, translate_errors

ISSUES_URL = "https://github.com/CloudSecurityAlliance/csa-skilljar/issues"


def register_feedback_tools(app: MCPServer, settings: Settings) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def report_a_problem(what_happened: str) -> ProblemReportOut:
        """Assemble a bug report about this server for the user to file.

        Call this when a tool is missing, a result contradicts its own description, or an
        error makes no sense - and when the user asks how to report something.

        Put what you actually observed in `what_happened`; that text is reproduced
        verbatim. The report carries the version, platform and active policy, and carries
        no Skilljar ids and no credential values, so the user can read it before filing.
        """
        creds = ["v2: set" if (settings.v2_client_id and settings.v2_client_secret) else "v2: unset",
                 "v1: set" if settings.v1_api_key else "v1: unset"]
        report = "\n".join([
            "## csa-skilljar problem report", "",
            f"- version: {__version__}",
            f"- python: {sys.version.split()[0]}",
            f"- platform: {platform.platform()}",
            f"- profile: {settings.profile}",
            f"- credentials configured: {', '.join(creds)}",
            "", "### What happened", "", what_happened.strip(), "",
            "_No Skilljar ids or credential values are included in this report._",
        ])
        return {"report": report, "where_to_file": ISSUES_URL}
