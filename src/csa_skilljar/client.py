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
    def credentials(self) -> Any | None:
        """The v2 credentials, when the backend has any.

        Exists so `check_access` does not have to reach through
        `client._backend._backend._creds` - which the Block 1 plan flagged as a wart
        with three layers of private attribute access. Returns None for a fake or
        credential-free backend rather than raising, because `check_access` must answer
        when nothing is configured.
        """
        inner = getattr(self._backend, "_backend", self._backend)
        return getattr(inner, "_creds", None)

    @property
    def policy(self) -> Policy | None:
        """The active policy, when the backend is policy-wrapped. `None` for a raw backend."""
        return getattr(self._backend, "policy", None)

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> dict[str, Any]:
        return self._backend.list_courses(title=title, cursor=cursor, page_size=page_size)

    def get_course(self, *, course_id: str) -> dict[str, Any]:
        return self._backend.get_course(course_id=course_id)
