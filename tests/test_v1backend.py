"""The v1 transport. Everything about it differs from v2, and the differences bite."""
import pytest

from csa_skilljar import exceptions as exc
from csa_skilljar.v1backend import (
    FakeV1Backend,
    V1Backend,
    V1Credentials,
    parse_page,
)

USERS = [{"user": {"id": "u1", "email": "ada@example.org", "first_name": "Ada",
                   "last_name": "Lovelace"},
          "signed_up_at": "2026-01-01T00:00:00Z", "registration_count": 3,
          "completion_count": 1, "latest_activity": "2026-06-01T00:00:00Z"}]

PROGRESS = {"u1": [
    {"published_course_id": "pc1", "domain_name": "learn.example.org",
     "enrolled_at": "2026-02-01T00:00:00Z", "enrollment_id": "e1", "certificate": None,
     "course": {"id": "c1", "title": "Zero Trust", "lesson_count": 10,
                "required_lesson_count": 8},
     "course_progress": {"completed_lesson_count": 4,
                         "completed_required_lesson_count": 3,
                         "credits_earned": "2", "credit_unit_plural": "CPEs",
                         "latest_activity": "2026-06-01T00:00:00Z",
                         "completed_at": None, "score": None, "max_score": None,
                         "success_status": None},
     "all_enrollments": [{"enrollment_id": "e1"}, {"enrollment_id": "e0"}]},
    # THE SAME COURSE, published to a second domain. This is the shape that made
    # Skilljar's by-id endpoint return the wrong record.
    {"published_course_id": "pc2", "domain_name": "training.example.org",
     "enrollment_id": "e2", "certificate": {"id": "cert1"},
     "course": {"id": "c1", "title": "Zero Trust", "lesson_count": 10},
     "course_progress": {"completed_lesson_count": 10, "completed_at": "2026-05-01"},
     "all_enrollments": [{"enrollment_id": "e2"}]},
]}


# --- trap 1: two envelope shapes -----------------------------------------------------

def test_both_v1_envelope_shapes_are_read():
    """v1 answers in two shapes and the caller cannot tell which is coming. A reader
    that assumes one silently returns NOTHING for the other - no error, empty list."""
    drf = parse_page({"count": 42, "next": None, "previous": None,
                      "results": [{"a": 1}, {"a": 2}]})
    assert drf["rows"] == [{"a": 1}, {"a": 2}]
    assert drf["total"] == 42

    bare = parse_page([{"a": 1}, {"a": 2}])
    assert bare["rows"] == [{"a": 1}, {"a": 2}]
    # None, not 0: a bare array does not SAY how many exist, which is a different fact
    # from saying there are none.
    assert bare["total"] is None


def test_a_single_object_is_one_row_not_zero():
    """GET /v1/users/{id} returns the object itself. Treating "no results key" as an
    empty page would report a learner who exists as one who does not."""
    one = parse_page({"user": {"id": "u1"}})
    assert len(one["rows"]) == 1
    assert one["total"] == 1


def test_a_body_that_is_neither_shape_is_an_error():
    with pytest.raises(exc.ApiError):
        parse_page("a string")
    with pytest.raises(exc.ApiError):
        parse_page({"count": 1, "results": "not a list"})


# --- trap 2: page numbers, not cursors ------------------------------------------------

def test_v1_paginates_by_page_number_not_cursor():
    """v2 hands back an opaque cursor; v1 hands back a URL with ?page=N. A
    cursor-shaped reader cannot page v1 at all."""
    page = parse_page({"count": 100, "previous": None, "results": [],
                       "next": "https://api.skilljar.com/v1/users?page=3"})
    assert page["has_more"] is True
    assert page["next_page"] == 3


def test_an_unreadable_next_link_is_an_error_not_a_last_page():
    """The silent version truncates every listing at page one and looks like a small
    dataset."""
    with pytest.raises(exc.ApiError):
        parse_page({"count": 100, "results": [],
                    "next": "https://api.skilljar.com/v1/users?page=not-a-number"})


def test_no_next_link_means_no_more_pages():
    page = parse_page({"count": 2, "next": None, "previous": None, "results": [{}, {}]})
    assert page["has_more"] is False and page["next_page"] is None


# --- trap 3: HTTP Basic with an EMPTY password ---------------------------------------

def test_v1_sends_basic_auth_with_an_empty_password():
    """The key is the USERNAME and the password is blank. Sent as a bearer token, or as
    the password, v1 returns 401 - which looks exactly like a bad key and sends people
    to reissue a credential that was fine."""
    import base64
    header = V1Credentials("KEY123").header()
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
    assert decoded == "KEY123:"
    assert decoded.endswith(":"), "the trailing colon is the empty password"


def test_the_v1_key_never_appears_in_a_repr():
    creds = V1Credentials("sk-live-DEADBEEF")
    assert "DEADBEEF" not in repr(creds)
    assert "DEADBEEF" not in repr(V1Backend(creds))


def test_an_empty_key_is_refused_at_construction():
    with pytest.raises(exc.CredentialsMissing):
        V1Credentials("")


# --- error translation ----------------------------------------------------------------

class Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


def backend_returning(resp):
    class Http:
        @staticmethod
        def get(url, params=None, headers=None):
            return resp
    return V1Backend(V1Credentials("k"), http=Http())


def test_a_401_names_the_basic_auth_scheme():
    """The remedy matters more than the status: the commonest cause is sending the key
    the way v2 wants it."""
    with pytest.raises(exc.CredentialsRejected) as e:
        backend_returning(Resp(401)).find_learner(email="a@b.c")
    assert "USERNAME" in str(e.value)


def test_a_404_says_the_endpoint_may_simply_not_exist():
    """v1 answers 404 for both "no such row" and "no such endpoint", and the published
    v1 document describes endpoints this deployment does not serve. "Not found" alone
    sends someone hunting for an id that was never the problem."""
    with pytest.raises(exc.NotFoundError) as e:
        backend_returning(Resp(404)).find_learner(email="a@b.c")
    assert "not served" in str(e.value)


def test_a_non_json_body_is_an_error():
    with pytest.raises(exc.ApiError):
        backend_returning(Resp(200)).find_learner(email="a@b.c")


# --- the fake matches the real shapes -------------------------------------------------

def test_the_fake_stores_raw_v1_shapes():
    """It holds the bare array and the DRF envelope as Skilljar sends them, and runs
    them through the same parse_page. A double storing the normalised shape would never
    exercise the normalisation - and the two-envelope trap is what breaks here."""
    fake = FakeV1Backend(users=USERS, progress=PROGRESS)
    found = fake.find_learner(email="ada@example.org")
    assert found["total"] == 1                       # DRF gives a count
    listed = fake.list_learner_progress(user_id="u1")
    assert listed["total"] is None                   # the bare array does not
    assert len(listed["rows"]) == 2


def test_the_v1_user_row_nests_the_learner():
    """The outer row is a SUMMARY; the learner is under `user`. A reader looking for
    `id` at the top level finds nothing."""
    fake = FakeV1Backend(users=USERS, progress=PROGRESS)
    row = fake.find_learner(email="ada@example.org")["rows"][0]
    assert "id" not in row
    assert row["user"]["id"] == "u1"


def test_an_unknown_learner_is_not_found():
    fake = FakeV1Backend(users=USERS, progress=PROGRESS)
    assert fake.find_learner(email="nobody@example.org")["rows"] == []
    with pytest.raises(exc.NotFoundError):
        fake.list_learner_progress(user_id="nope")


# --- the by-id endpoint that returns the wrong record ---------------------------------

def test_selecting_by_publication_survives_a_course_on_two_domains():
    """Skilljar's own by-id endpoint resolves by the UNDERLYING COURSE, so a course
    published twice returns a different domain's record with a 200. Both fixtures share
    course c1 deliberately: this asserts each id returns ITS OWN publication."""
    fake = FakeV1Backend(users=USERS, progress=PROGRESS)
    for pcid, domain in (("pc1", "learn.example.org"), ("pc2", "training.example.org")):
        row = fake.get_learner_progress(user_id="u1", published_course_id=pcid)["rows"][0]
        assert row["published_course_id"] == pcid
        assert row["domain_name"] == domain


def test_a_course_the_learner_is_not_in_says_how_many_they_have():
    fake = FakeV1Backend(users=USERS, progress=PROGRESS)
    with pytest.raises(exc.NotFoundError) as e:
        fake.get_learner_progress(user_id="u1", published_course_id="pc-nope")
    assert "2 enrolments" in str(e.value)
