"""Offline tests for the server's self-presentation.

The AI on the other side sees only two things: the tool manifest and (on
hosts that surface it, opencode >= 1.17.10) the server instructions. A
server that under-declares gets bypassed in favour of redis-cli and
config-file hunting — which cannot work when the Redis port is not
exposed. These tests keep the identity honest. No network needed.
"""

from __future__ import annotations

import pytest

from pra_mcp.registry import ONLY_PATH

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "redis_info",
    "redis_servers",
    "redis_use_server",
    "redis_keys",
    "redis_export",
    "redis_get",
    "redis_set",
    "redis_delete",
    "redis_ttl",
}


async def test_server_declares_identity(server_session):
    info = server_session.server_info
    assert info.name == "phpredisadmin"
    assert info.description, "server description must not be empty"
    assert "Redis" in info.description


async def test_instructions_orient_the_ai(server_session):
    instructions = server_session.instructions
    assert instructions, "instructions must be set for hosts that surface them"
    # Jurisdiction: the reason models bypass this server is that nothing told
    # them redis-cli cannot work here.
    assert "redis-cli" in instructions
    assert "only" in instructions.lower()
    # Orientation: the entry-point tools must be named so the model can chain them.
    for tool in ("redis_servers", "redis_use_server", "redis_keys", "redis_get"):
        assert tool in instructions


async def test_all_tools_registered(mcp_client):
    tools = (await mcp_client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_every_tool_claims_jurisdiction(mcp_client):
    """ONLY_PATH rides along in every docstring, for hosts that drop
    instructions and models that only skim the tool list."""
    tools = (await mcp_client.list_tools()).tools
    for t in tools:
        assert ONLY_PATH in t.description, f"{t.name} lost its identity clause"
