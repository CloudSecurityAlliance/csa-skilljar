"""Python client and MCP server for the Skilljar customer education platform."""
from __future__ import annotations

from .backend import Backend, FakeBackend, V2Backend
from .client import SkilljarClient
from .policy import ALL_CAPABILITIES, PROFILES, Policy, PolicyBackend

__version__ = "0.9.0"

__all__ = ["ALL_CAPABILITIES", "PROFILES", "Backend", "FakeBackend", "Policy",
           "PolicyBackend", "SkilljarClient", "V2Backend", "__version__"]
