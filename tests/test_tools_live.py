"""Live integration tests against a real phpRedisAdmin instance.

Skipped unless both PRA_LIVE and PRA_URL are set, so a PRA_URL that
happens to point at production never gets hit by accident:

    PRA_LIVE=1 PRA_URL=https://pra.example.com PRA_USER=... PRA_PASS=... \\
        uv run pytest tests/test_tools_live.py

The second milestone will drive these against the starchat-gama test Redis.
Only safe operations (info/keys/get/set/delete on keys we created) are used;
no flush or destructive commands.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not (os.environ.get("PRA_URL") and os.environ.get("PRA_LIVE")),
        reason="set PRA_LIVE=1 and PRA_URL to run live tests",
    ),
]


@pytest.fixture(autouse=True)
def _fresh_client():
    from pra_mcp.http_client import reset_client

    reset_client()
    yield
    reset_client()


async def test_server_info(mcp_client):
    result = await mcp_client.call_tool("redis_info", {})
    text = result.content[0].text
    assert "Redis" in text or "redis_version" in text


async def test_tools_advertised(mcp_client):
    result = await mcp_client.list_tools()
    names = {t.name for t in result.tools}
    assert {
        "redis_info",
        "redis_keys",
        "redis_get",
        "redis_set",
        "redis_delete",
        "redis_export",
        "redis_servers",
        "redis_use_server",
    } <= names
