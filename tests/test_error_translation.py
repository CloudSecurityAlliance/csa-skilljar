"""Every library error must reach the user with its message intact.

MCP's SDK turns any non-`ToolError` into an `UnexpectedToolError` and DISCARDS the
message, so the user sees "Error executing tool X" and nothing about what went wrong.
That is invariant 2 in CLAUDE.md, and it fails silently: the tool call errors either
way, and only the text differs.
"""
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar import exceptions as exc
from csa_skilljar.mcp._tools._base import translate_errors


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


ALL_ERRORS = sorted(set(_subclasses(exc.SkilljarError)), key=lambda c: c.__name__)


def _instantiate(cls):
    """Every error type takes a message; ScopeError needs its own arguments."""
    if cls is exc.ScopeError:
        return cls("the token lacks a scope", required="courses:read", granted=set())
    return cls("distinctive marker text")


@pytest.mark.parametrize("error_type", ALL_ERRORS, ids=lambda c: c.__name__)
def test_every_error_subclass_survives_translation_with_its_message(error_type):
    """Fail-closed over the exception hierarchy, the same shape as policy._GATES: a new
    error type is covered the moment it is defined, without anyone remembering to add
    it here."""
    @translate_errors
    def boom():
        raise _instantiate(error_type)

    with pytest.raises(ToolError) as caught:
        boom()
    message = str(caught.value)
    assert message, f"{error_type.__name__} translated to an empty message"
    assert "Error executing tool" not in message
    # The original text must be in there somewhere - a translation that replaces the
    # message with a generic one is as useless as no translation.
    original = str(_instantiate(error_type))
    assert original in message, (
        f"{error_type.__name__}: the original message {original!r} was dropped")


def test_at_least_the_known_error_types_are_covered():
    """Guards the guard: if the hierarchy is refactored so nothing subclasses
    SkilljarError, the parametrised test above silently becomes zero test cases."""
    names = {c.__name__ for c in ALL_ERRORS}
    assert {"AuthError", "CredentialsMissing", "CredentialsRejected", "ScopeError",
            "NotFoundError", "ConflictError", "PolicyError", "ApiError"} <= names
    assert len(ALL_ERRORS) >= 8


def test_a_plain_exception_is_left_alone():
    """Only the library's own errors are translated. Swallowing arbitrary exceptions
    would hide real bugs behind a tidy message."""
    @translate_errors
    def boom():
        raise RuntimeError("a genuine bug")

    with pytest.raises(RuntimeError):
        boom()
