import contextlib
import io

from csa_skilljar.mcp._config import ClientProvider, settings_from_env
from csa_skilljar.mcp.server import create_server


def test_building_the_server_writes_nothing_to_stdout():
    """Under stdio, stdout IS the JSON-RPC channel. One stray byte corrupts the session
    and the server looks alive while answering nothing."""
    buf = io.StringIO()
    settings = settings_from_env({})
    with contextlib.redirect_stdout(buf):
        create_server(ClientProvider(settings), settings=settings)
    assert buf.getvalue() == "", f"something wrote to stdout: {buf.getvalue()!r}"
