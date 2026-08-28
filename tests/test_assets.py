"""The asset library, and the presigned URL that is the whole point of this block."""
import inspect

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from csa_skilljar.backend import FakeBackend
from csa_skilljar.client import SkilljarClient
from csa_skilljar.mcp._tools.assets import register_asset_tools
from csa_skilljar.policy import Policy, PolicyBackend
from csa_skilljar.v1backend import FakeV1Backend

# Shaped like the real rows: `type` not `asset_type`, aspect_ratio 16:9 on EVERYTHING
# including the PDF, and download_url present only because the fake strips it on listing.
ASSETS = [
    {"id": "a1", "name": "ACSP_Module_1.pdf", "type": "PDF", "aspect_ratio": "16:9",
     "embed_link_url": "", "sync_completion": False,
     "download_url": "https://everpath-course-content.s3.amazonaws.com/x.pdf"
                     "?AWSAccessKeyId=AKIA&Expires=1787956708&Signature=sig"},
    {"id": "a2", "name": "Intro video", "type": "VIDEO_BOTR", "aspect_ratio": "16:9",
     "embed_link_url": "https://cdn.example/embed", "sync_completion": True,
     "download_url": "https://everpath-course-content.s3.amazonaws.com/v.mp4?Signature=s"},
]


def build(profile="parity", with_v1=True):
    policy = Policy.from_profile(profile)
    v1 = PolicyBackend(FakeV1Backend(assets=ASSETS), policy) if with_v1 else None
    client = SkilljarClient(PolicyBackend(FakeBackend(), policy), v1=v1)
    app = MCPServer(name="t")
    register_asset_tools(app, lambda: client)
    return {n: t.fn for n, t in app._tool_manager._tools.items()}


@pytest.fixture
def tools():
    return build()


# --- trap 3: only the detail view carries a link --------------------------------------

def test_list_does_not_carry_a_download_url(tools):
    """The real listing omits it. A caller who lists, sees no URL, and concludes the
    file is unavailable is the failure this asymmetry causes."""
    out = tools["list_assets"]()
    assert out["assets"]
    for row in out["assets"]:
        assert "download_url" not in row
        assert "warning" not in row
    assert "no download_url" in out["note"]


def test_get_carries_the_link_and_the_warning(tools):
    row = tools["get_asset"](id="a1")
    assert row["download_url"].startswith("https://everpath-course-content.s3")
    assert "PRESIGNED" in row["warning"]


# --- traps 1 and 2: what the URL actually is ------------------------------------------

def test_download_url_is_described_as_a_bearer_capability(tools):
    """Verified live: a ranged GET with NO authorization returned 206 and the file's
    content type. The URL is not a reference to the file, it IS the file - so the
    description has to say that, because the consequence lands in a transcript or a
    ticket where nothing in this server can reach it."""
    doc = inspect.getdoc(tools["get_asset"]) or ""
    assert "IS THE FILE, NOT A REFERENCE TO IT" in doc
    assert "NO Skilljar credentials" in doc
    assert "Anyone who can read the URL can download the content" in doc


def test_the_url_is_documented_as_unstable_and_uncacheable(tools):
    """It changes on every fetch and expires in about an hour. A stored URL later looks
    like a broken asset rather than an expired link."""
    doc = inspect.getdoc(tools["get_asset"]) or ""
    assert "different every time" in doc
    assert "do not store or cache it" in doc.lower()
    assert "expires" in doc.lower()


def test_the_warning_travels_with_the_url_not_just_the_docs(tools):
    """A model that never read the description still gets told, because the warning is
    in the payload beside the thing it is about."""
    row = tools["get_asset"](id="a2")
    assert "do not paste it" in row["warning"].lower()
    assert "expires" in row["warning"].lower() or "hour" in row["warning"].lower()


# --- trap 4: a meaningless field is not surfaced --------------------------------------

def test_aspect_ratio_is_not_presented_as_meaningful_for_documents(tools):
    """`16:9` on all 157 assets in the reference org, PDFs included. It is a default,
    not a measurement, and returning it invites a model to report a PDF's aspect ratio
    as a fact about the document."""
    assert "aspect_ratio" not in tools["get_asset"](id="a1")
    for row in tools["list_assets"]()["assets"]:
        assert "aspect_ratio" not in row


# --- naming ----------------------------------------------------------------------------

def test_type_is_renamed_to_avoid_colliding_with_json_api_type(tools):
    """Every v2 resource carries a JSON:API `type`. One word meaning two things across
    the two backends is how a caller reads the wrong field."""
    row = tools["get_asset"](id="a1")
    assert row["asset_type"] == "PDF"
    assert "type" not in row


# --- ordinary behaviour -----------------------------------------------------------------

def test_the_listing_surfaces_v1s_total(tools):
    assert tools["list_assets"]()["total"] == 2


def test_an_unknown_asset_is_not_found(tools):
    with pytest.raises(ToolError) as e:
        tools["get_asset"](id="nope")
    assert "not found" in str(e.value).lower()


def test_an_empty_id_is_refused(tools):
    with pytest.raises(ToolError):
        tools["get_asset"](id="")


def test_without_a_v1_key_the_error_names_the_variable():
    tools = build(with_v1=False)
    with pytest.raises(ToolError) as e:
        tools["list_assets"]()
    assert "CSA_SKILLJAR_V1_API_KEY" in str(e.value)


def test_assets_share_the_content_read_gate():
    """list_lessons already returns content_asset_id under content.read. A stricter gate
    here would leave a caller able to see the reference and unable to resolve it."""
    # `people`, not `reporting` - reporting INCLUDES content.read, so it would have
    # passed this test without the gate doing anything.
    tools = build(profile="people")
    with pytest.raises(ToolError) as e:
        tools["list_assets"]()
    assert "content.read" in str(e.value)
