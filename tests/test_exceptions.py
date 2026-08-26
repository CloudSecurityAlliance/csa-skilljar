from csa_skilljar import exceptions as exc


def test_hierarchy_roots_at_skilljar_error():
    for cls in (exc.AuthError, exc.NotFoundError, exc.PolicyError, exc.ApiError):
        assert issubclass(cls, exc.SkilljarError)


def test_credentials_errors_are_auth_errors():
    assert issubclass(exc.CredentialsMissing, exc.AuthError)
    assert issubclass(exc.CredentialsRejected, exc.AuthError)
    assert issubclass(exc.ScopeError, exc.AuthError)


def test_scope_error_carries_required_and_granted():
    e = exc.ScopeError("nope", required="question-banks:write", granted=("courses:read",))
    assert e.required == "question-banks:write"
    assert e.granted == ("courses:read",)
    assert "question-banks:write" in str(e)


def test_api_error_carries_status():
    e = exc.ApiError("boom", status=503)
    assert e.status == 503


def test_repr_never_leaks_a_secret():
    # A credential must never reach a log line via an exception repr.
    e = exc.CredentialsRejected("v2 client rejected")
    assert "secret" not in repr(e).lower()
