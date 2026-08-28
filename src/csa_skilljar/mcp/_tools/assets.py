"""The asset library — the files a course is made of. v1-only; v2 has no assets endpoint.

One property dominates this module. `get_asset` returns a `download_url` that is a
**presigned S3 link**: it works with no Skilljar credentials at all, for about an hour,
and it is different on every fetch. Verified against the live API on 2026-08-28 with a
ranged GET carrying no authorization header — `206`, `application/pdf`,
`bytes 0-0/7455694`.

That makes the URL a bearer capability rather than a reference. Anyone who reads it can
download the file, so one pasted into a transcript, a ticket or a screenshot is a working
link to course content for whoever sees it. Every description here says so, and the
result carries a `warning` field, because the consequence lands outside this system where
no control here can reach it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer

from ...client import SkilljarClient
from .._schemas import AssetListOut, AssetOut
from ._base import READ, translate_errors

_DOWNLOAD_WARNING = (
    "download_url is a PRESIGNED link: it needs no Skilljar credentials, works for "
    "about an hour, and is different every time it is fetched. Treat it as the file "
    "itself - do not paste it anywhere it will be read by someone who should not have "
    "the content, and do not store it, because it expires.")
_LIST_NOTE = ("Not paginated in practice - the whole library comes back. Listings carry "
              "no download_url; use get_asset for that.")


def _flatten(row: dict[str, Any], *, with_url: bool) -> AssetOut:
    out: dict[str, Any] = {"id": row.get("id", "")}
    for key in ("name", "embed_link_url", "sync_completion"):
        if key in row:
            out[key] = row[key]
    # Renamed on the way out: `type` collides with the JSON:API `type` that every v2
    # resource carries, and one word meaning two things across the two backends is how
    # a caller ends up reading the wrong field.
    if "type" in row:
        out["asset_type"] = row["type"]
    # `aspect_ratio` is DELIBERATELY NOT SURFACED. It is "16:9" on all 157 assets in the
    # reference org, PDFs included - a default rather than a measurement. Returning it
    # would invite a model to report a document's aspect ratio as a fact about it.
    if with_url and row.get("download_url"):
        out["download_url"] = row["download_url"]
        out["warning"] = _DOWNLOAD_WARNING
    return cast(AssetOut, out)


def register_asset_tools(app: MCPServer,
                         get_client: Callable[[], SkilljarClient]) -> None:

    @app.tool(annotations=READ)
    @translate_errors
    def list_assets() -> AssetListOut:
        """List the organization's asset library - the files courses are built from.

        v2 has no assets endpoint at all, so this is the only way to see what content
        exists. `list_lessons` returns a `content_asset_id`; this is what resolves it.

        `asset_type` is PDF, FILE, VIDEO_BOTR or TEMPLATE. `sync_completion` means the
        lesson is marked complete when the learner finishes the asset rather than when
        they navigate away.

        NO DOWNLOAD LINKS HERE. The listing carries no `download_url` - only
        `get_asset` does. An empty result for one does not mean the file is unavailable.

        The whole library comes back in one response; there is no paging to do.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        page = get_client().list_assets()
        out: AssetListOut = {
            "assets": [_flatten(r, with_url=False) for r in page["rows"]],
            "note": _LIST_NOTE}
        if page.get("total") is not None:
            out["total"] = page["total"]
        return out

    @app.tool(annotations=READ)
    @translate_errors
    def get_asset(id: str) -> AssetOut:
        """Fetch one asset, INCLUDING A WORKING DOWNLOAD LINK.

        `id` is the asset id, as `list_assets` returns and as a lesson's
        `content_asset_id` refers to.

        THE RETURNED download_url IS THE FILE, NOT A REFERENCE TO IT. It is a presigned
        link that needs NO Skilljar credentials and works for roughly an hour, and it is
        different every time this is called.
        Anyone who can read the URL can download the content.

        So: do not put it anywhere it will be seen by someone who should not have the
        file, and do not store or cache it - a saved URL expires and then looks like a
        broken asset rather than an expired link.

        If you only need to know an asset exists, or what type it is, use `list_assets`,
        which returns no link at all.

        Requires `CSA_SKILLJAR_V1_API_KEY`, a separate credential from the v2 client.
        """
        if not id:
            raise ValueError("id is required - the asset id, from list_assets")
        page = get_client().get_asset(asset_id=id)
        return _flatten(page["rows"][0], with_url=True)
