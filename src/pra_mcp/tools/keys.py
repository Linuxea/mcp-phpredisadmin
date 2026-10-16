"""Key listing and bulk export tools."""

from __future__ import annotations

import json

from ..http_client import get_client
from ..parsing import extract_keys
from ..registry import mcp


@mcp.tool()
def redis_keys(filter: str = "") -> str:
    """List Redis keys (optionally filtered by substring) without fetching values."""
    client = get_client()
    params = client.qs()
    if filter:
        params["filter"] = filter
    r = client.get("index.php", params=params, timeout=60)
    r.raise_for_status()
    keys = set()
    for k in extract_keys(r.text):
        if not filter or filter.lower() in k.lower():
            keys.add(k)
    if not keys:
        return "no keys found (or page requires login — run redis_info to check auth)"
    return json.dumps(sorted(keys), ensure_ascii=False, indent=1)


@mcp.tool()
def redis_export(filter: str = "") -> str:
    """Dump all keys (optionally filtered by substring) with values as one JSON object. Heavy: use sparingly."""
    client = get_client()
    data: dict[str, str] = {"type": "json"}
    if filter:
        data["filter"] = filter
    r = client.post("export.php", data=data)
    return r.text
