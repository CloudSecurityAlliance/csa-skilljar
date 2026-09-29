"""Every v1 backend method reaches the v1 API, with the credential Skilljar actually accepts.

v1 has no scope table and no token, so there is no pre-check to catch a malformed path. What
takes its place is the census itself: every method is called against a recording transport,
and a method that builds an unreachable path shows up as a request that was never made.

The credential is the other half, and it is the subtler one. Skilljar's v1 scheme is HTTP
Basic with the API key as the USERNAME and an EMPTY password. Sending it as a bearer token,
or as the password, returns 401 - which looks exactly like a bad key and sends somebody to
reissue a credential that was fine. So the header is asserted byte for byte, once, rather
than trusted to look right.
"""
from __future__ import annotations

import base64
import inspect

import httpx
import pytest
import respx

from csa_skilljar import exceptions as exc
from csa_skilljar.v1backend import V1Backend, V1Credentials

KEY = "sj-v1-DEADBEEF"
PAGE = {"count": 0, "next": None, "previous": None, "results": []}

# Values a name alone cannot supply. `domain_name` has to look like a domain because v1
# selects a publication by it, and `email` has to look like an address for the same reason.
OVERRIDES = {"domain_name": "training.example.org", "email": "someone@example.org",
             "slug": "enrollment.created"}


def argument_for(parameter: str):
    if parameter in OVERRIDES:
        return OVERRIDES[parameter]
    if parameter.endswith("_id"):
        return "x1"
    return "x"


def methods() -> list[str]:
    return sorted(n for n in dir(V1Backend) if not n.startswith("_"))


def call(backend: V1Backend, name: str):
    signature = inspect.signature(getattr(V1Backend, name))
    kwargs = {p: argument_for(p) for p, value in signature.parameters.items()
              if p != "self" and value.default is inspect.Parameter.empty}
    return getattr(backend, name)(**kwargs)


def test_the_census_covers_every_method(request):
    """The guard on the guard: if `methods()` ever returns a subset, the census shrinks and
    nothing says so."""
    names = methods()
    assert len(names) >= 27, f"V1Backend has {len(names)} methods; the census expects 27+"
    assert "find_learner" in names and "list_webhooks" in names


@respx.mock
def test_every_method_sends_a_request_and_gets_an_envelope_back():
    """One catch-all. A method whose path could not be built, or which returned something the
    envelope parser refuses, fails here and names itself."""
    route = respx.route().mock(return_value=httpx.Response(200, json=PAGE))
    backend = V1Backend(V1Credentials(KEY))

    failures = []
    for name in methods():
        before = route.call_count
        try:
            call(backend, name)
        except exc.NotFoundError:
            # `get_learner_progress` selects locally from a listing and raises when the
            # learner has no matching enrolment, which an empty fixture guarantees. The
            # REQUEST still went out, which is what the census is about.
            pass
        except Exception as error:                # noqa: BLE001 - collected, not raised
            failures.append(f"{name}: {type(error).__name__}: {error}")
            continue
        if route.call_count == before:
            failures.append(f"{name}: made no request at all")

    assert failures == [], "\n  ".join(["these v1 methods did not reach the API:", *failures])


@respx.mock
def test_the_key_is_the_username_and_the_password_is_empty():
    """The trailing colon is load-bearing. `base64("key:")`, not `base64("key")` and not a
    bearer token - both of the wrong forms return 401, which is indistinguishable from a bad
    key and sends somebody to reissue a credential that works."""
    route = respx.get("https://api.skilljar.com/v1/paths").mock(
        return_value=httpx.Response(200, json=PAGE))
    V1Backend(V1Credentials(KEY)).list_paths()

    sent = route.calls[0].request.headers["Authorization"]
    assert sent == "Basic " + base64.b64encode(f"{KEY}:".encode()).decode()
    assert not sent.startswith("Bearer ")


def test_an_absent_key_is_refused_before_anything_is_built():
    """v1 has no token exchange, so a missing key would otherwise surface as a 401 from the
    first call - an authorization failure standing in for a configuration one."""
    with pytest.raises(exc.CredentialsMissing):
        V1Credentials("")


@respx.mock
def test_selecting_an_enrolment_locally_reports_what_it_looked_through():
    """`get_learner_progress` filters a full listing in memory rather than asking the API,
    because v1's filtered form matched the wrong publication for one domain in fifty-four -
    right until the exact case where a domain matters, and a wrong 200 is worse than a 404.

    So the refusal has to say how many it saw, or "not found" is indistinguishable from
    "the listing was empty because something else broke"."""
    respx.get("https://api.skilljar.com/v1/users/u1/published-courses").mock(
        return_value=httpx.Response(200, json={
            "count": 2, "next": None, "previous": None,
            "results": [{"published_course_id": "other1"},
                        {"published_course_id": "other2"}]}))

    with pytest.raises(exc.NotFoundError) as ei:
        V1Backend(V1Credentials(KEY)).get_learner_progress(
            user_id="u1", published_course_id="wanted")

    message = str(ei.value)
    assert "wanted" in message and "u1" in message
    assert "2 enrolments" in message
    assert "list_learner_progress" in message, "the refusal must name how to see them"


@respx.mock
def test_a_matching_enrolment_comes_back_as_a_single_row_envelope():
    respx.get("https://api.skilljar.com/v1/users/u1/published-courses").mock(
        return_value=httpx.Response(200, json={
            "count": 2, "next": None, "previous": None,
            "results": [{"published_course_id": "other"},
                        {"published_course_id": "wanted", "progress": 42}]}))

    out = V1Backend(V1Credentials(KEY)).get_learner_progress(
        user_id="u1", published_course_id="wanted")

    assert out["rows"] == [{"published_course_id": "wanted", "progress": 42}]
    assert out["total"] == 1 and out["has_more"] is False
