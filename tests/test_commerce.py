"""Commerce — read-only by design, and the family where paging actually matters."""
import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.commerce import register_commerce_tools
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

# 60 codes: enough that the default page of 25 leaves more behind, which is the whole
# behaviour under test.
CODES = [{"id": f"pc{i}", "code": f"CODE{i}", "active": i % 3 != 0,
          "max_uses": None if i % 5 else 10, "use_count": i % 4,
          "promo_code_pool_id": "pool1" if i < 30 else "pool2"} for i in range(60)]
POOLS = [{"id": "pool1", "name": "Launch 2026", "active": True, "percent_off": 25,
          "price_cents": None, "starts_at": "2026-01-01", "expires_at": "2026-12-31",
          "expire_content": False},
         {"id": "pool2", "name": "Renewal", "active": False, "percent_off": None,
          "price_cents": 9900, "starts_at": None, "expires_at": None,
          "expire_content": True}]
OFFERS = [{"id": "o1", "sku": "CCSK-V5", "offer_type": "COURSE", "active": True,
           "currency_code": "USD", "price_cents": 39500, "price_credits": None,
           "domain_name": "learn.example.org", "published_course_id": "pc1",
           "published_path_id": None, "course_series_id": None,
           "max_quantity": None, "starts_at": None, "ends_at": None}]
CREDITS = [{"id": "tc1", "training_credit_code": "ACME-2026",
            "tracking_identifier": "PO-4471", "credits_total": 100, "credits_used": 40,
            "expiration_date": "2026-12-31", "expire_content": False}]
PURCHASES = [{"id": "pur1", "total_cents": 39500, "currency_code": "USD"}]


def build(profile="reporting", with_v1=True):
    policy = Policy.from_profile(profile)
    v1 = PolicyBackend(FakeV1Backend(promo_codes=CODES, promo_code_pools=POOLS,
                                     offers=OFFERS, credit_codes=CREDITS,
                                     purchases=PURCHASES), policy) if with_v1 else None
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy), v1=v1)
    app = MCPServer(name="t")
    register_commerce_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- scale: the point of this family --------------------------------------------------

def test_the_default_page_is_far_smaller_than_the_servers(tools):
    """v1 defaults to 250 and honours page_size=1000. A tool that inherited that would
    put thousands of rows into a conversation to answer "are there any promo codes"."""
    out = tools["list_promo_codes"]()
    assert len(out["rows"]) == 25
    assert out["total"] == 60
    assert out["has_more"] is True


def test_total_answers_how_many_without_fetching_them(tools):
    """The question is nearly always "how many" or "does this one exist", and both are
    answerable from one small page."""
    out = tools["list_promo_codes"]()
    assert out["total"] == 60
    assert len(out["rows"]) < out["total"]
    assert "without fetching them all" in out["note"]


def test_an_oversized_page_is_refused_with_the_reason(tools):
    """v1 will happily return 1000 rows. Refusing here is the only place it can be
    stopped, and the message has to say what to do instead."""
    with pytest.raises(ToolError) as e:
        tools["list_promo_codes"](page_size=1000)
    assert "1000 rows" in str(e.value)
    assert "Read `total` instead" in str(e.value)


def test_paging_is_by_number_and_advances(tools):
    first = tools["list_promo_codes"](page_size=10)
    second = tools["list_promo_codes"](page_size=10, page=2)
    assert first["page"] == 1 and second["page"] == 2
    assert [r["id"] for r in first["rows"]] != [r["id"] for r in second["rows"]]
    assert first["next_page"] == 2


def test_the_last_page_reports_no_more(tools):
    out = tools["list_promo_codes"](page_size=250)
    assert out["has_more"] is False
    assert "next_page" not in out


# --- filters answer the real questions -------------------------------------------------

def test_an_exact_code_lookup(tools):
    """The usual question: is the code a customer quoted real?"""
    out = tools["list_promo_codes"](filter_code="CODE7")
    assert [r["code"] for r in out["rows"]] == ["CODE7"]


def test_active_splits_valid_from_spent(tools):
    active = tools["list_promo_codes"](filter_active=True)["total"]
    inactive = tools["list_promo_codes"](filter_active=False)["total"]
    assert active + inactive == 60


def test_filter_by_pool(tools):
    assert tools["list_promo_codes"](filter_promo_code_pool_id="pool2")["total"] == 30


def test_unlimited_uses_is_documented_as_distinct_from_none_left(tools):
    """`max_uses: null` means unlimited. Reading it as zero remaining inverts the
    meaning of the field."""
    doc = inspect.getdoc(tools["list_promo_codes"]) or ""
    assert "NOT the same as zero remaining" in doc


# --- where the money actually lives ----------------------------------------------------

def test_the_pool_carries_the_discount_not_the_code(tools):
    """"How much is this code worth" is a question about the POOL. The code row carries
    only its own usage, so a caller looking there finds nothing and may report no
    discount."""
    code = tools["list_promo_codes"](filter_code="CODE1")["rows"][0]
    assert "percent_off" not in code and "price_cents" not in code
    pool = tools["list_promo_code_pools"](filter_name="Launch 2026")["rows"][0]
    assert pool["percent_off"] == 25
    assert "carries the DISCOUNT" in (inspect.getdoc(tools["list_promo_code_pools"]) or "")


def test_offers_explain_which_kind_of_thing_is_sold(tools):
    doc = inspect.getdoc(tools["list_offers"]) or ""
    assert "exactly one of which is set" in doc
    assert "discounts live in promo-code pools" in doc


def test_credit_codes_are_a_balance_not_a_discount(tools):
    doc = inspect.getdoc(tools["list_training_credit_codes"]) or ""
    assert "carries a BALANCE" in doc
    row = tools["list_training_credit_codes"](filter_tracking_identifier="PO-4471")["rows"][0]
    assert row["credits_total"] - row["credits_used"] == 60


# --- purchases cannot be searched ------------------------------------------------------

def test_get_purchase_says_there_is_no_way_to_search(tools):
    """v1 has no purchase listing at all. A model that reports "I could not find the
    purchase" implies a search that does not exist."""
    doc = inspect.getdoc(tools["get_purchase"]) or ""
    assert "NO WAY TO LIST OR SEARCH PURCHASES" in doc
    assert "webhook" in doc
    assert "Say that rather than searching" in doc


def test_get_purchase_without_an_id_explains_where_one_comes_from(tools):
    with pytest.raises(ToolError) as e:
        tools["get_purchase"](id="")
    assert "no listing endpoint" in str(e.value)


def test_get_purchase_by_id_works(tools):
    assert tools["get_purchase"](id="pur1")["total_cents"] == 39500


# --- read-only by design ---------------------------------------------------------------

def test_no_commerce_tool_writes():
    """ADR-007 calls this family read-biased: a promo code is money, and the useful
    question is what exists, not make more. This asserts the module never grew a write."""
    from csa_skilljar.mcp._tools import commerce
    src = inspect.getsource(commerce)
    for verb in ("create_", "update_", "delete_", "issue_", "revoke_"):
        assert f"def {verb}" not in src, f"a {verb}* tool appeared in a read-only family"


def test_commerce_is_not_in_the_parity_profile():
    """`parity` mirrors the official server, which has NO commerce tools. Granting it
    there would quietly change what the word means."""
    from csa_skilljar import policy as P
    assert P.READ_COMMERCE not in P.PROFILES["parity"]


def test_commerce_is_refused_without_the_capability():
    tools = build(profile="parity")
    with pytest.raises(ToolError) as e:
        tools["list_offers"]()
    assert "commerce.read" in str(e.value)


def test_without_a_v1_key_the_error_names_the_variable():
    tools = build(with_v1=False)
    with pytest.raises(ToolError) as e:
        tools["list_offers"]()
    assert "CSA_SKILLJAR_V1_API_KEY" in str(e.value)
