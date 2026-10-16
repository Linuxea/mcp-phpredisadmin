"""Read/write/delete tools for individual keys."""

from __future__ import annotations

from ..http_client import get_client
from ..parsing import strip_html
from ..registry import mcp


@mcp.tool()
def redis_get(key: str) -> str:
    """Get the full value of a Redis key as JSON. Works for string/hash/list/set/zset."""
    client = get_client()
    r = client.post(
        "export.php", params={**client.qs(), "key": key}, data={"type": "json"}
    )
    return r.text


@mcp.tool()
def redis_set(
    key: str,
    value: str,
    type: str = "string",
    hkey: str = "",
    index: str = "",
    score: str = "",
) -> str:
    """Create/overwrite a Redis key. type: string|hash|list|set|zset.
    hash requires hkey; list requires index ('' append, -1 prepend, N overwrite); zset requires numeric score."""
    client = get_client()
    data: dict[str, str] = {"type": type, "key": key, "value": value}
    if hkey:
        data["hkey"] = hkey
    if index != "":
        data["index"] = index
    if score != "":
        data["score"] = score
    r = client.post("edit.php", data=data)
    if "exception" in r.text or "ERROR" in r.text:
        return f"FAILED: {strip_html(r.text)[:500]}"
    return f"OK: {type} key '{key}' saved"


@mcp.tool()
def redis_delete(key: str) -> str:
    """Delete a Redis key."""
    client = get_client()
    r = client.post(
        "delete.php", params={**client.qs(), "key": key}, data={"post": "1"}
    )
    return (
        f"OK: '{key}' deleted" if "?view" in r.text else f"Response: {r.text[:200]}"
    )
