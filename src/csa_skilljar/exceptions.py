"""Typed errors. One translation layer at the MCP boundary turns these into `ToolError`.

Never interpolate a credential into a message: these objects are logged by embedders.
"""
from __future__ import annotations


class SkilljarError(Exception):
    """Base for everything this package raises."""


class AuthError(SkilljarError):
    """Any credential problem. Subclasses distinguish the remedy."""


class CredentialsMissing(AuthError):
    """The credential is not configured at all."""


class CredentialsRejected(AuthError):
    """The credential is configured but upstream refused it."""


class ScopeError(AuthError):
    """The credential is valid but lacks the scope this operation needs."""

    def __init__(self, message: str, *, required: str, granted: tuple[str, ...] = ()) -> None:
        self.required = required; self.granted = tuple(granted)
        super().__init__(f"{message} (needs `{required}`)")


class NotFoundError(SkilljarError):
    """The resource does not exist, or is not in the caller's organization."""


class PolicyError(SkilljarError):
    """The local policy refused this operation. Not an upstream failure."""


class ApiError(SkilljarError):
    """An upstream failure that is not one of the typed cases above."""

    def __init__(self, message: str, *, status: int = 0) -> None:
        self.status = status
        super().__init__(message)
