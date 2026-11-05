"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def mcp_client():
    """In-memory MCP client connected to our server object (no subprocess, no port).

    Requires `pytest.mark.anyio` on the test. Only tool *calls* reach the
    network — listing tools etc. stays local.
    """
    from mcp import Client

    from pra_mcp import mcp

    async with Client(mcp, raise_exceptions=True) as c:
        yield c


@pytest.fixture
def server_session(mcp_client):
    """The initialize-result session: server_info / instructions / capabilities.

    SDK v2's high-level ``Client`` exposes no public accessor for it, so the
    private ``_session`` attribute is funneled through this one fixture — when
    an SDK 2.x rename breaks it, fix here first.
    """
    return mcp_client._session
