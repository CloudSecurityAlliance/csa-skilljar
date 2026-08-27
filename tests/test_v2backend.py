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


# --- by-id paths and the scope template ------------------------------------------

@respx.mock
def test_get_course_hits_the_interpolated_path():
    route = respx.get("https://api.skilljar.com/v2/courses/abc123").mock(
        return_value=httpx.Response(200, json={"data": {"type": "courses", "id": "abc123"}}))
    out = V2Backend(creds()).get_course(course_id="abc123")
    assert out["data"]["id"] == "abc123"
    assert route.call_count == 1


@respx.mock
def test_a_by_id_read_still_enforces_the_scope_pre_check():
    """Scope lookup is by LITERAL spec path, so /v2/courses/abc123 never matches
    /v2/courses/{id}. Without passing the template, this control fails open silently -
    every by-id read would skip its scope check and nothing would say so."""
    route = respx.get("https://api.skilljar.com/v2/courses/abc123")
    with pytest.raises(exc.ScopeError) as e:
        V2Backend(creds(scope="lessons:read")).get_course(course_id="abc123")
    assert e.value.required == "courses:read"
    assert route.call_count == 0, "the pre-check must fire before any request"


@respx.mock
def test_an_unknown_by_id_template_is_a_loud_error():
    """The other half: if a template is passed but is not in the generated scope table,
    that is a bug in this package and must not be mistaken for 'needs no scope'."""
    b = V2Backend(creds())
    with pytest.raises(exc.ApiError) as e:
        b._get("/v2/coursez/abc", template="/v2/coursez/{id}")
    assert "not a known v2 operation" in str(e.value)


@respx.mock
def test_get_course_404_is_a_typed_not_found():
    respx.get("https://api.skilljar.com/v2/courses/nope").mock(
        return_value=httpx.Response(404, json={}))
    with pytest.raises(exc.NotFoundError):
        V2Backend(creds()).get_course(course_id="nope")
