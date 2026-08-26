from csa_skilljar import scopes


def test_list_courses_requires_courses_read():
    assert scopes.scopes_for("GET", "/v2/courses/") == ("courses:read",)


def test_questions_are_any_of_two_scopes():
    got = scopes.scopes_for("GET", "/v2/questions/")
    assert set(got) == {"question-banks:read", "quizzes:read"}


def test_pre_auth_endpoints_require_nothing():
    assert scopes.scopes_for("POST", "/v2/auth/token") == ()


def test_unknown_operation_returns_empty_not_raises():
    assert scopes.scopes_for("GET", "/v2/not-a-thing/") == ()


def test_table_is_not_empty_and_covers_the_spec():
    # Guards against a generation run that silently produced nothing.
    assert len(scopes.REQUIRED_SCOPE) >= 70


def test_generated_table_is_in_sync_with_the_spec():
    """Refreshing specs/ without regenerating scopes.py must fail CI, not pass quietly.

    The scope pre-check is only as good as this table: a stale entry means either
    refusing a call that would have worked, or letting one through to fail upstream
    with a worse message. Same reasoning as scripts/check_docs.py - a generated
    artifact that can silently drift from its source is not a guard.
    """
    import sys
    sys.path.insert(0, "scripts")
    from gen_scopes import build_table

    assert build_table() == scopes.REQUIRED_SCOPE, (
        "scopes.py is stale - run: .venv/bin/python scripts/gen_scopes.py"
    )
