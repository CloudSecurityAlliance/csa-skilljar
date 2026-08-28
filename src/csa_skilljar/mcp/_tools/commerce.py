"""Commerce — promo codes, pools, offers, training credits and purchases.

v1-only: **v2 has no commerce surface at all**, so there is no routing question here.

READ-ONLY, and that is a decision rather than a consequence of the write freeze (ADR-007
calls this family "read-biased"). The reference organization holds 13,708 promo codes
across 4,290 pools. Creating or deleting those in bulk is not something to hand an agent:
a promo code is money, a mistake is visible to customers, and the useful question is
almost always "what exists and is it still valid", not "make more".

The other thing this family teaches is scale. These are the only v1 endpoints where
paging genuinely happens — 13,708 rows is 55 pages at the server's default of 250, and
`page_size=1000` really does return 1000. So every tool here:

  * defaults to a SMALL page, not the server's 250
  * always reports `total`, so the size of a set is answerable without fetching it
  * says which page it returned and whether more exist

Answering "how many promo codes are there" by pulling 13,708 rows into a conversation is
the failure this shape is designed against.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import CommerceListOut
from ._base import READ, translate_errors

# Deliberately far below the server's 250. A model asking "what promo codes exist" wants
# to know the shape and the total, not to read every row.
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 250

_SCALE_NOTE = ("`total` is the size of the WHOLE set, not this page. Use it to answer "
               "'how many' without fetching them all - this organization has thousands "
               "of promo codes.")


def _page_out(page: dict[str, Any], requested: int | None, note: str) -> CommerceListOut:
    out: CommerceListOut = {"rows": page["rows"], "note": f"{note} {_SCALE_NOTE}"}
    if page.get("total") is not None:
        out["total"] = page["total"]
    out["page"] = requested or 1
    out["has_more"] = bool(page.get("has_more"))
    if page.get("next_page") is not None:
        out["next_page"] = page["next_page"]
    return out


def _check_size(page_size: int | None) -> int:
    size = page_size or _DEFAULT_PAGE_SIZE
    if not 1 <= size <= _MAX_PAGE_SIZE:
        raise ValueError(
            f"page_size must be between 1 and {_MAX_PAGE_SIZE}; got {size}. v1 will "
            f"honour far larger values - it returns 1000 rows for page_size=1000 - "
            f"which is how a listing floods a conversation. Read `total` instead if you "
            f"need the size of the set.")
    return size


def register_commerce_tools(app: MCPServer,
                            get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_promo_codes(filter_active: bool | None = None,
                         filter_code: str | None = None,
                         filter_promo_code_pool_id: str | None = None,
                         page: int | None = None,
                         page_size: int | None = None) -> CommerceListOut:
        """List discount codes. READ-ONLY - nothing here creates or revokes one.

        THERE ARE THOUSANDS. This organization has over 13,000 promo codes; do not try
        to read them all. `total` answers "how many" on its own, and the filters below
        answer nearly every real question without paging at all.

        `filter_code` looks up one code exactly - the usual question, when someone asks
        whether a code a customer quoted is real.
        `filter_active` splits valid from expired or exhausted.
        `filter_promo_code_pool_id` narrows to one campaign; `list_promo_code_pools`
        finds the pool.

        `use_count` against `max_uses` says whether a code is spent. A null `max_uses`
        means unlimited, which is NOT the same as zero remaining.

        Pages default to 25 rather than v1's 250. `page` is a number, not a cursor.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        size = _check_size(page_size)
        got = get_client().list_promo_codes(
            active=filter_active, code=filter_code,
            promo_code_pool_id=filter_promo_code_pool_id, page=page, page_size=size)
        return _page_out(got, page, "Discount codes.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_promo_code_pools(filter_name: str | None = None,
                              filter_offer_id: str | None = None,
                              page: int | None = None,
                              page_size: int | None = None) -> CommerceListOut:
        """List promo-code pools - the campaigns individual codes belong to.

        A pool carries the DISCOUNT and the VALIDITY WINDOW; the codes in it carry only
        their own usage. So "how much is this code worth" is a question about the pool,
        not the code.

        `percent_off` and `price_cents` are alternatives: a pool sets one or the other.
        `starts_at` / `expires_at` bound when codes in it can be redeemed, and
        `expire_content` says whether access granted through the pool expires too - a
        different thing from the code expiring.

        Over 4,000 pools here. Read `total` rather than paging through them.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        size = _check_size(page_size)
        got = get_client().list_promo_code_pools(
            name=filter_name, offer_id=filter_offer_id, page=page, page_size=size)
        return _page_out(got, page, "Promo-code pools - the campaigns codes belong to.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_offers(page: int | None = None,
                    page_size: int | None = None) -> CommerceListOut:
        """List what is for sale, and at what price.

        An offer binds a price to something purchasable - `published_course_id`,
        `published_path_id` or `course_series_id`, exactly one of which is set. Which one
        tells you what kind of thing is being sold.

        `price_cents` is in the offer's own `currency_code`; `price_credits` is the
        training-credit price, and an offer may have either or both. Neither is a
        discounted price - discounts live in promo-code pools.

        `starts_at` / `ends_at` bound availability, and `active` can be false
        independently of the dates.

        There are no filters on this endpoint; page through, or read `total`.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        size = _check_size(page_size)
        return _page_out(get_client().list_offers(page=page, page_size=size), page,
                         "Offers - what is for sale and at what price.")

    @app.tool(annotations=READ)
    @translate_errors
    def list_training_credit_codes(filter_tracking_identifier: str | None = None,
                                   filter_training_credit_code: str | None = None,
                                   page: int | None = None,
                                   page_size: int | None = None) -> CommerceListOut:
        """Find prepaid training-credit balances and how much is left on them.

        Different from a promo code: a promo code discounts a purchase, a training-credit
        code carries a BALANCE that is spent down. `credits_used` against `credits_total`
        says how much is left.

        `tracking_identifier` is the customer-side reference, usually a PO or contract
        number, and is the field to search when someone asks about "their credits".

        `expire_content` says whether access bought with the credits expires when the
        code does - a separate question from the balance running out.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        size = _check_size(page_size)
        got = get_client().list_training_credit_codes(
            tracking_identifier=filter_tracking_identifier,
            training_credit_code=filter_training_credit_code, page=page, page_size=size)
        return _page_out(got, page, "Training-credit codes - prepaid balances.")

    @app.tool(annotations=READ)
    @translate_errors
    def get_purchase(id: str) -> dict[str, Any]:
        """Fetch one purchase by id. THERE IS NO WAY TO LIST OR SEARCH PURCHASES.

        v1 offers only this by-id endpoint - no listing, no filter, no search. So the id
        has to come from somewhere else: a purchase-fulfillment webhook payload, an order
        reference a customer quotes, or a record already held outside Skilljar.

        If you do not have an id, this tool cannot help and no other tool here can find
        one. Say that rather than searching - "I could not find the purchase" would imply
        a search that is not possible.

        A purchase record concerns a real person's transaction. Report what was asked and
        no more.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not id:
            raise ValueError(
                "id is required - the purchase id. There is no listing endpoint, so it "
                "must come from a webhook payload or an order reference you already have.")
        return get_client().get_purchase(purchase_id=id)["rows"][0]
