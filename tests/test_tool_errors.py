import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar import exceptions as exc
from csa_skilljar.mcp._tools._base import translate_errors


@pytest.mark.parametrize("raised,fragment", [
    (exc.CredentialsMissing("set CSA_SKILLJAR_V2_CLIENT_ID"), "CSA_SKILLJAR_V2_CLIENT_ID"),
    (exc.CredentialsRejected("rotated"), "rotated"),
    (exc.ScopeError("nope", required="courses:write"), "courses:write"),
    (exc.PolicyError("profile does not enable it"), "profile"),
    (exc.NotFoundError("no such course"), "no such course"),
    (exc.ApiError("upstream 503", status=503), "503"),
    (ValueError("page_size must be positive"), "page_size"),
])
def test_every_typed_error_becomes_a_toolerror_with_the_message_intact(raised, fragment):
    """A plain exception becomes UnexpectedToolError with the message DISCARDED, so
    every sentence written to help the user is thrown away at the boundary."""
    @translate_errors
    def tool():
        raise raised

    with pytest.raises(ToolError) as e:
        tool()
    assert fragment in str(e.value)


def test_the_decorator_preserves_the_signature_for_the_sdk():
    @translate_errors
    def tool(filter_title: str | None = None) -> str:
        return "ok"

    import inspect
    assert "filter_title" in inspect.signature(tool).parameters
    assert tool.__wrapped__ is not None
