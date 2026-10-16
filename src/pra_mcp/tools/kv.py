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


_VALID_TYPES = ("string", "hash", "list", "set", "zset")


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
    hash requires hkey; zset requires numeric score. list index: '' append,
    N overwrite (N==len appends), -1 prepend on newer phpRedisAdmin (appends on older ones)."""
    client = get_client()
    # Validate locally: edit.php silently skips writes whose branch conditions
    # are not met but still renders its success page (verified live).
    if type not in _VALID_TYPES:
        return f"FAILED: unknown type '{type}' (expected one of: {', '.join(_VALID_TYPES)})"
    if type == "hash" and not hkey:
        return "FAILED: type hash requires hkey"
    if type == "zset" and score == "":
        return "FAILED: type zset requires score"
    if type == "zset":
        try:
            float(score)
        except ValueError:
            return f"FAILED: zset score must be numeric, got {score!r}"

    data: dict[str, str] = {"type": type, "key": key, "value": value}
    if hkey:
        data["hkey"] = hkey
    if type == "list":
        # edit.php's list branch requires isset($_POST['index']); omitting the
        # field (the old behaviour) turned every plain append into a silent no-op.
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
