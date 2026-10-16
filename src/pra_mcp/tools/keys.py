"""Key listing and bulk export tools.

Full-keyspace operations are refused by design: this MCP server is callable
by an LLM, and a filterless keys()/export() means KEYS('*') server-side,
blown-up contexts client-side (the ~5k-key instance this was built against
timed out at 30s on a full export). Every listing therefore requires an
explicit filter and is capped.
"""

from __future__ import annotations

import fnmatch
import json

from ..http_client import get_client
from ..parsing import extract_keys
from ..registry import mcp

# Refuse patterns that would match the whole keyspace.
_FULL_SCAN_PATTERNS = {"", "*", "%", "**", "?*"}

MAX_LISTED_KEYS = 200
MAX_EXPORTED_KEYS = 50


def _reject_full_scan(filter: str) -> str | None:
    """Return a refusal message for full-keyspace patterns, else None."""
    if filter.strip().strip("*?") == "":
        return (
            "refusing full-keyspace scan: pass a specific filter "
            f"(got {filter!r}); e.g. a key prefix like 'user:42:'"
        )
    return None


def _matches(key: str, filter: str) -> bool:
    """glob characters activate fnmatch, otherwise substring match."""
    if any(c in filter for c in "*?["):
        return fnmatch.fnmatchcase(key, filter)
    return filter.lower() in key.lower()


def _list_keys(filter: str) -> list[str]:
    """Fetch the sidebar page and filter client-side.

    This instance ignores the GET filter param, so filtering here is both
    the semantics and the safety net.
    """
    client = get_client()
    r = client.get("index.php", params=client.qs(), timeout=60)
    r.raise_for_status()
    return [k for k in extract_keys(r.text) if _matches(k, filter)]


@mcp.tool()
def redis_keys(filter: str) -> str:
    """List Redis keys matching a filter, without fetching values.
    Filter is required and must be specific (substring or glob like 'user:*' or 'user:?0');
    full-keyspace patterns are refused. Returns at most 200 keys."""
    if (refusal := _reject_full_scan(filter)):
        return refusal
    keys = _list_keys(filter)
    if not keys:
        return f"no keys found matching {filter!r}"
    if len(keys) > MAX_LISTED_KEYS:
        return (
            f"{len(keys)} keys match {filter!r} (showing first {MAX_LISTED_KEYS}); "
            "narrow the filter to see the rest"
        ) + "\n" + json.dumps(sorted(keys)[:MAX_LISTED_KEYS], ensure_ascii=False, indent=1)
    return json.dumps(sorted(keys), ensure_ascii=False, indent=1)


@mcp.tool()
def redis_export(filter: str) -> str:
    """Dump values for keys matching a filter as one JSON object.
    Filter is required (substring or glob); at most 50 keys are exported —
    narrow the filter or use redis_get per key for more."""
    if (refusal := _reject_full_scan(filter)):
        return refusal
    keys = sorted(_list_keys(filter))
    if not keys:
        return f"no keys found matching {filter!r}"
    if len(keys) > MAX_EXPORTED_KEYS:
        return (
            f"refusing export of {len(keys)} keys (max {MAX_EXPORTED_KEYS}); "
            "narrow the filter or fetch keys individually with redis_get"
        )
    # Deliberately NOT export.php's all-keys mode: it runs KEYS('*') plus a
    # value fetch per key server-side and times out on large keyspaces.
    # Single-key export.php calls are fast and bounded by the cap above.
    client = get_client()
    out: dict[str, object] = {}
    for k in keys:
        r = client.post(
            "export.php", params={**client.qs(), "key": k}, data={"type": "json"}
        )
        try:
            out[k] = json.loads(r.text)
        except json.JSONDecodeError:
            out[k] = r.text  # keep raw text rather than failing the whole dump
    return json.dumps(out, ensure_ascii=False, indent=1)
