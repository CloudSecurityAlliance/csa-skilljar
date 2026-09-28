"""Every v2 backend method reaches a KNOWN operation — and the id never becomes the label.

`_check_scope` looks a path up in the generated scope table, and the lookup is by LITERAL
SPEC PATH. `/v2/courses/{id}` is in the table; `/v2/courses/abc123` is not. So a method that
interpolates an id into its path and forgets to pass `template=` hands the pre-check a path it
cannot find — and ZD-2 made that raise rather than shrug, because the alternative is a scope
check that silently passes for every call it was meant to govern.

That is one invariant, and it applies to all eighty-one methods identically. So it is tested
once, across all of them, rather than eighty-one times by hand:

* **Membership is derived** from the `Backend` protocol. A method added to the protocol and to
  no override table is still called, with arguments derived from its own signature — so the
  census cannot fall behind the code, which is the failure mode of every hand-kept list.
* **The arguments are derived too**, by parameter name. They do not need to be realistic: what
  is under test is the PATH each method builds and the template it declares, and a request that
  never leaves the process cannot care whether the id is plausible.

The whole thing is one respx catch-all: if any method builds an unknown spec path, the call
raises and names itself.
"""
from __future__ import annotations

import base64
import inspect
import json
import time

import httpx
import pytest
import respx

from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import Backend, V2Backend

ENVELOPE = {"data": [], "has_more": False, "next_cursor": None}

# Arguments a derived value cannot get right, by method and parameter. Kept deliberately
# small: every entry is a place the census had to be told something, and a long table here
# would mean the derivation is not pulling its weight.
OVERRIDES: dict[str, dict[str, object]] = {
    "complete_enrollments": {"send_notifications": False},
}


def any_token_scope_undeclared():
    """A JWT with no `scope` claim.

    `granted_scopes()` then returns None, which means "the token does not declare its scopes"
    - NOT "it declares none". `_check_scope` treats that as "cannot tell", so every operation
    passes the pre-check and the census is about the PATH rather than about scopes, which have
    their own tests.
    """
    def seg(payload):
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600})}.sig"


def credentials():
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": any_token_scope_undeclared()}))
    return V2Credentials("id", "sk-live-DEADBEEF")


def argument_for(method_name: str, parameter: str):
    """A value shaped by the parameter's NAME, which is the only thing a census can know."""
    override = OVERRIDES.get(method_name, {})
    if parameter in override:
        return override[parameter]
    if parameter.endswith("_ids") or parameter in ("emails",):
        return ["x1"] if parameter.endswith("_ids") else ["someone@example.org"]
    if parameter.endswith("_id"):
        return "x1"
    if parameter == "items":
        return [{"id": "x1"}]
    if parameter == "changes":
        return {"name": "renamed"}
    return "x"


def protocol_methods() -> list[str]:
    return sorted(n for n in dir(Backend) if not n.startswith("_"))


def call(backend: V2Backend, name: str):
    """Invoke `name` with an argument per REQUIRED parameter and nothing else.

    Only the required ones, so each method builds its shortest path - which is the one most
    likely to have been written by hand and least likely to have been exercised.
    """
    signature = inspect.signature(getattr(Backend, name))
    kwargs = {p: argument_for(name, p)
              for p, value in signature.parameters.items()
              if p != "self" and value.default is inspect.Parameter.empty}
    return getattr(backend, name)(**kwargs)


def test_the_census_covers_the_whole_protocol():
    """The guard on the guard. `protocol_methods()` is what the test below iterates, so if it
    ever returns a subset the census silently shrinks and nothing says so."""
    names = protocol_methods()
    assert len(names) >= 81, f"the protocol has {len(names)} methods; the census expects 81+"
    assert "list_courses" in names and "update_students" in names


@respx.mock
def test_every_method_builds_a_path_the_scope_table_knows():
    """The invariant, for all of them at once.

    A method that interpolates an id without declaring a `template=` produces a spec path the
    table does not contain, and `_check_scope` raises `ApiError` naming it. Before ZD-2 it did
    not: an unknown path read as "declared, needs no scope", so a typo disabled the pre-check
    for that operation and said nothing.
    """
    # The token route is registered FIRST, because respx matches in registration order and
    # the catch-all below would otherwise answer the token grant with an empty envelope.
    backend = V2Backend(credentials())
    respx.route().mock(return_value=httpx.Response(200, json=ENVELOPE))

    failures = []
    for name in protocol_methods():
        try:
            call(backend, name)
        except Exception as error:                # noqa: BLE001 - collected, not raised
            failures.append(f"{name}: {type(error).__name__}: {error}")

    assert failures == [], (
        "these methods did not reach a known v2 operation - most likely an id interpolated "
        "into the path without a matching `template=`, which silently skips the scope "
        "pre-check:\n  " + "\n  ".join(failures))


@respx.mock
def test_a_path_with_an_id_is_requested_with_the_id_and_checked_against_the_template():
    """The two halves that must differ. The REQUEST carries the real id, because that is the
    resource being asked for; the SCOPE LOOKUP carries the template, because the table is
    keyed on spec paths. Conflating them either way breaks one of the two."""
    route = respx.get("https://api.skilljar.com/v2/courses/abc123").mock(
        return_value=httpx.Response(200, json=ENVELOPE))
    V2Backend(credentials()).get_course(course_id="abc123")

    assert route.called, "the request must use the interpolated path"
    assert str(route.calls[0].request.url).endswith("/v2/courses/abc123")


@respx.mock
def test_a_template_that_is_not_in_the_table_is_refused_before_any_request():
    """The ZD-2 behaviour itself, forced. An unknown spec path raises, names the path, and
    says where the table comes from - and no request is made, so a mistyped template cannot
    reach the network with its scope check skipped."""
    from csa_skilljar import exceptions as exc

    route = respx.get("https://api.skilljar.com/v2/not-a-real-endpoint/")
    backend = V2Backend(credentials())

    with pytest.raises(exc.ApiError) as ei:
        backend._get("/v2/not-a-real-endpoint/")

    message = str(ei.value)
    assert "/v2/not-a-real-endpoint/" in message
    assert "not a known v2 operation" in message
    assert "gen_scopes.py" in message, "the remedy has to name how the table is regenerated"
    assert route.call_count == 0, "a request was made despite an unknown operation"
