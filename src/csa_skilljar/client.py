"""`SkilljarClient` - the library entry point. The MCP server is one consumer of it."""
from __future__ import annotations

from typing import Any

from .backend import Backend
from .policy import Policy, PolicyBackend


class SkilljarClient:
    """Thin, typed surface over a (policy-wrapped) Backend."""

    def __init__(self, backend: Backend | PolicyBackend) -> None:
        self._backend = backend

    @property
    def policy(self) -> Policy | None:
        """The active policy, when the backend is policy-wrapped. `None` for a raw backend."""
        return getattr(self._backend, "policy", None)

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_courses(title=title, cursor=cursor, page_size=page_size)
