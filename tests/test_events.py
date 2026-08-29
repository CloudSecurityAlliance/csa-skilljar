"""Webhooks — a redaction problem — and ten endpoints compressed into one tool."""
import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.events import EVENT_TYPES, register_event_tools
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

# Shaped like the live rows, INCLUDING the secrets Skilljar really returns. Distinctive
# values, so a leak anywhere is unmistakable.
SECRET_HEADER = "sk-live-HEADERSECRET-32-chars-xx"
URL_TOKEN = "sk-live-URLTOKEN-in-query-string"
BASIC_PW = "sk-live-BASICPASSWORD-do-not-leak"

WEBHOOKS = [
    {"id": "w1", "event_type": "COURSE_COMPLETION", "active": True,
     "deactivate_reason": None,
     "target_url": f"https://cloudsecurityalliance.org/hook?auth={URL_TOKEN}",
     "additional_headers": {"X-Skilljar-Secret": SECRET_HEADER},
     "basic_auth_username": "svc", "basic_auth_password": BASIC_PW},
    {"id": "w2", "event_type": "PURCHASE_FULFILLMENT", "active": False,
     "deactivate_reason": "too many delivery failures",
     "target_url": "https://exams.example.org/hook",
     "additional_headers": {}, "basic_auth_username": "", "basic_auth_password": ""},
]
# One row per sample, matching the live shape: `results` is a LIST of one payload.
SAMPLES = {slug: {"event_type": slug, "user": {"id": "sample-id"}, "example": True}
           for slug in EVENT_TYPES.values()}
SECRETS = (SECRET_HEADER, URL_TOKEN, BASIC_PW)


def build(profile="full", with_v1=True):
    policy = Policy.from_profile(profile)
    v1 = PolicyBackend(FakeV1Backend(webhooks=WEBHOOKS, samples=SAMPLES), policy) \
        if with_v1 else None
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy), v1=v1)
    app = MCPServer(name="t")
    register_event_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- the redaction, which is the point ------------------------------------------------

def test_no_secret_reaches_the_listing(tools):
    """Verified live: Skilljar returns a 32-char X-Skilljar-Secret in plaintext, an
    `auth` token in the target URL query, and a basic_auth_password field. All three are
    credentials for whatever the webhook authenticates to."""
    blob = repr(tools["list_webhooks"]())
    for secret in SECRETS:
        assert secret not in blob, "a webhook secret reached the tool output"


def test_no_secret_reaches_the_detail_view(tools):
    blob = repr(tools["get_webhook"](id="w1"))
    for secret in SECRETS:
        assert secret not in blob


def test_header_names_survive_but_values_do_not(tools):
    """"There is an X-Skilljar-Secret header" answers where an event goes and how it
    authenticates in shape. Its value is the credential itself."""
    row = tools["get_webhook"](id="w1")
    assert row["additional_header_names"] == ["X-Skilljar-Secret"]
    assert "additional_headers" not in row


def test_the_url_keeps_host_and_path_but_loses_the_query(tools):
    """Two of three live targets carry a token in the query string, so the whole query
    goes - but the parameter NAMES stay, because "the URL has an auth parameter" is
    useful and its value is not."""
    row = tools["get_webhook"](id="w1")
    assert row["target_url"] == "https://cloudsecurityalliance.org/hook"
    assert row["target_url_query_parameters_withheld"] == ["auth"]


def test_a_basic_auth_password_is_replaced_not_omitted(tools):
    """Omitting it silently would read as "no password set", which is a different fact
    about the webhook."""
    row = tools["get_webhook"](id="w1")
    assert row["basic_auth_password"] == "<withheld by csa-skilljar>"
    assert row["basic_auth_username"] == "svc"


def test_a_webhook_with_no_password_does_not_claim_a_withheld_one(tools):
    row = tools["get_webhook"](id="w2")
    assert "basic_auth_password" not in row


def test_the_withholding_is_stated_not_silent(tools):
    """A reader must know a secret exists and was withheld, or they will conclude the
    webhook has none and go looking for a bug."""
    assert "WITHHELD" in tools["list_webhooks"]()["note"]
    assert "Skilljar Dashboard" in (inspect.getdoc(tools["list_webhooks"]) or "")


def test_the_fake_really_holds_the_secrets():
    """Guards the guard: if the fixture stopped carrying secrets, every test above would
    pass while proving nothing."""
    from csa_skilljar.v1backend import FakeV1Backend as F
    raw = repr(F(webhooks=WEBHOOKS).list_webhooks()["rows"])
    for secret in SECRETS:
        assert secret in raw, "the fixture must contain what the tools must not emit"


# --- ten endpoints, one tool ------------------------------------------------------------

def test_every_skilljar_event_type_is_covered():
    """v1 has one sample endpoint per event type. If Skilljar adds an eleventh and this
    map is not updated, the tool cannot reach it - so the count is pinned."""
    assert len(EVENT_TYPES) == 10
    assert "COURSE_COMPLETION" in EVENT_TYPES
    assert EVENT_TYPES["PURCHASE_FULFILLMENT"] == "purchase-fulfillment"


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_each_event_type_resolves_to_a_payload(tools, event_type):
    out = tools["preview_event_payload"](event_type=event_type)
    assert out["event_type"] == event_type
    assert out["example_payload"] is not None


def test_event_type_is_forgiving_about_case_and_dashes(tools):
    """The value appears as COURSE_COMPLETION on a webhook and course-completion in the
    URL. A caller holding either should not have to know which this wants."""
    for spelling in ("course_completion", "COURSE-COMPLETION", " Course_Completion "):
        assert tools["preview_event_payload"](
            event_type=spelling)["event_type"] == "COURSE_COMPLETION"


def test_an_unknown_event_type_lists_the_real_ones(tools):
    with pytest.raises(ToolError) as e:
        tools["preview_event_payload"](event_type="COURSE_STARTED")
    assert "COURSE_COMPLETION" in str(e.value)


def test_the_sample_is_labelled_as_not_real(tools):
    """The payload contains ids that refer to nothing. A model that looks them up finds
    nothing and may report a data problem that does not exist."""
    out = tools["preview_event_payload"](event_type="QUIZ_COMPLETION")
    assert "refer to no real record" in out["note"]
    assert "NOT A REAL EVENT" in (inspect.getdoc(tools["preview_event_payload"]) or "")


# --- a dead webhook looks like a healthy one --------------------------------------------

def test_a_deactivated_webhook_reports_why(tools):
    row = tools["get_webhook"](id="w2")
    assert row["active"] is False
    assert row["deactivate_reason"] == "too many delivery failures"
    assert "deactivate_reason" in (inspect.getdoc(tools["list_webhooks"]) or "")


# --- gating -------------------------------------------------------------------------------

def test_webhooks_need_their_own_capability():
    """Not content.read: the configuration is where events go and how they authenticate."""
    tools = build(profile="parity")
    with pytest.raises(ToolError) as e:
        tools["list_webhooks"]()
    assert "events.read" in str(e.value)


def test_without_a_v1_key_the_error_names_the_variable():
    with pytest.raises(ToolError) as e:
        build(with_v1=False)["list_webhooks"]()
    assert "CSA_SKILLJAR_V1_API_KEY" in str(e.value)
