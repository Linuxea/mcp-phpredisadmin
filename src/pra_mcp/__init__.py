"""mcp-phpredisadmin: operate Redis through a phpRedisAdmin web UI via MCP."""

from __future__ import annotations

import os

from . import tools  # noqa: F401  # importing registers the tools
from .registry import mcp


def main() -> None:
    if not os.environ.get("PRA_URL"):
        raise SystemExit("PRA_URL env var is required, e.g. https://pra.example.com")
    mcp.run(transport="stdio")


__all__ = ["mcp", "main"]
