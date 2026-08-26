"""Shared tool machinery: error translation and annotations."""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ... import exceptions as exc

F = TypeVar("F", bound=Callable[..., Any])

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False)


def translate_errors(fn: F) -> F:
    """Turn the library's typed errors into readable `ToolError`s.

    Must raise the SDK's `ToolError`: anything else becomes `UnexpectedToolError` whose
    message the SDK deliberately suppresses, so the user sees "Error executing tool X"
    and nothing about what actually went wrong.
    """
    @functools.wraps(fn)          # keeps __wrapped__ so the SDK reads the real signature
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except exc.AuthError as e:
            # Covers CredentialsMissing / CredentialsRejected / ScopeError, each of which
            # already carries its own remedy in the message.
            raise ToolError(str(e)) from e
        except exc.PolicyError as e:
            raise ToolError(str(e)) from e
        except exc.NotFoundError as e:
            raise ToolError(f"not found: {e}") from e
        except exc.ApiError as e:
            raise ToolError(f"Skilljar rejected the request: {e}") from e
        except ValueError as e:
            # The library raises plain ValueError for a bad argument value. Without this
            # clause each becomes an UnexpectedToolError with the message dropped, so the
            # model sees "Error executing tool X" and cannot correct itself.
            raise ToolError(f"invalid argument: {e}") from e
    return wrapped  # type: ignore[return-value]
