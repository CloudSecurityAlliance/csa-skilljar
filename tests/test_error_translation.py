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


# ---------------------------------------------------------------------------
# The page_size floor (#102)
# ---------------------------------------------------------------------------
# `test_pagination.py` asserts the guard holds across all twenty-nine tools that take the
# argument. These are the decorator's own unit tests: the cases a tool cannot reach,
# because the MCP SDK dispatches from a JSON object and therefore always calls with
# keyword arguments.


def test_page_size_is_rejected_when_passed_positionally():
    """The SDK never does this; our own code and tests can. A guard that reads only
    `kwargs` would pass a zero straight through here, and silently - which is the same
    shape of hole #102 was."""
    @translate_errors
    def listing(course_id, page_size=None):
        return page_size

    with pytest.raises(ToolError, match="page_size must be 1 or greater"):
        listing("co0", 0)
    assert listing("co0", 5) == 5


def test_page_size_is_rejected_when_it_is_keyword_only():
    """A keyword-only `page_size` has no position, so the index must not be mistaken for
    one: `args[3]` on a call with three positional arguments is a different argument
    entirely, and comparing THAT to 1 would refuse valid calls."""
    @translate_errors
    def listing(course_id, *, page_size=None):
        return page_size

    with pytest.raises(ToolError, match="page_size must be 1 or greater"):
        listing("co0", page_size=0)
    assert listing("co0", page_size=5) == 5
    assert listing("co0") is None


def test_a_tool_without_page_size_is_untouched():
    """The check must cost nothing and do nothing for the tools it does not concern -
    including one that happens to take a positional argument where `page_size` sits on
    its neighbours."""
    @translate_errors
    def unpaginated(course_id):
        return course_id

    assert unpaginated("co0") == "co0"
    assert unpaginated(0) == 0          # not mistaken for a page size


def test_the_message_survives_translation():
    """It is raised inside the try so it takes the ValueError clause, which is what keeps
    the wording identical to the inline guards it replaced."""
    @translate_errors
    def listing(page_size=None):
        return page_size

    with pytest.raises(ToolError, match="invalid argument: page_size must be 1 or greater"):
        listing(page_size=-3)
