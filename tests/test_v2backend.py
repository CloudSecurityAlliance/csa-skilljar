import base64
import json
import time

import httpx
import pytest
import respx

from csa_skilljar import exceptions as exc
from csa_skilljar.auth import V2Credentials
from csa_skilljar.backend import V2Backend


def make_jwt(scope="courses:read"):
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': time.time() + 3600, 'scope': scope})}.sig"


def creds(scope="courses:read"):
    respx.post("https://api.skilljar.com/v2/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": make_jwt(scope)}))
    return V2Credentials("id", "sk-live-DEADBEEF")


@respx.mock
def test_list_courses_sends_bearer_and_returns_the_envelope():
    route = respx.get("https://api.skilljar.com/v2/courses/").mock(
        return_value=httpx.Response(200, json={"data": [{"type": "courses", "id": "c1"}],
                                               "has_more": False, "next_cursor": None}))
    out = V2Backend(creds()).list_courses()
    assert out["data"][0]["id"] == "c1"
    assert route.calls[0].request.headers["Authorization"].startswith("Bearer ")


@respx.mock
def test_filters_and_pagination_map_to_query_params():
    route = respx.get("https://api.skilljar.com/v2/courses/").mock(
        return_value=httpx.Response(200, json={"data": [], "has_more": False, "next_cursor": None}))
    V2Backend(creds()).list_courses(title="zero", cursor="abc", page_size=50)
    q = route.calls[0].request.url.params
    assert q["filter[title]"] == "zero"
    assert q["page[cursor]"] == "abc"
    assert q["page[size]"] == "50"


@respx.mock
def test_omitted_params_are_not_sent_at_all():
    """Sending filter[title]= empty is not the same as omitting it."""
    route = respx.get("https://api.skilljar.com/v2/courses/").mock(
        return_value=httpx.Response(200, json={"data": [], "has_more": False, "next_cursor": None}))
    V2Backend(creds()).list_courses()
    assert str(route.calls[0].request.url.params) == ""


@respx.mock
def test_missing_scope_is_refused_locally_with_no_http_call():
    route = respx.get("https://api.skilljar.com/v2/courses/")
    with pytest.raises(exc.ScopeError):
        V2Backend(creds(scope="lessons:read")).list_courses()
    assert route.call_count == 0, "the pre-check must fire before any request"


@respx.mock
def test_404_becomes_not_found_error():
    respx.get("https://api.skilljar.com/v2/courses/").mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(exc.NotFoundError):
        V2Backend(creds()).list_courses()


@respx.mock
def test_401_becomes_credentials_rejected():
    respx.get("https://api.skilljar.com/v2/courses/").mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(exc.CredentialsRejected):
        V2Backend(creds()).list_courses()


@respx.mock
def test_500_becomes_api_error_carrying_the_status():
    respx.get("https://api.skilljar.com/v2/courses/").mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(exc.ApiError) as e:
        V2Backend(creds()).list_courses()
    assert e.value.status == 503


@respx.mock
def test_unreachable_host_is_an_api_error():
    respx.get("https://api.skilljar.com/v2/courses/").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(exc.ApiError):
        V2Backend(creds()).list_courses()
