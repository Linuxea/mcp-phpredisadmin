"""Server-info and server-switching tools."""

from __future__ import annotations

from ..http_client import get_client
from ..parsing import find_server_select, parse_server_options, strip_html
from ..registry import mcp


@mcp.tool()
def redis_info() -> str:
    """Redis server info (version, memory, clients, keyspace) via phpRedisAdmin."""
    client = get_client()
    r = client.get("info.php", timeout=30)
    r.raise_for_status()
    return strip_html(r.text)[:4000]


@mcp.tool()
def redis_servers() -> str:
    """List all Redis servers configured in phpRedisAdmin, marking the current one."""
    client = get_client()
    r = client.get("index.php", params=client.qs(), timeout=30)
    r.raise_for_status()
    select = find_server_select(r.text)
    if not select:
        return (
            "no server selector found (single-server setup or old version); current s="
            + client.server_id
        )
    out = []
    for opt in parse_server_options(select):
        mark = "  <- current" if opt.selected or opt.value == client.server_id else ""
        out.append(f"s={opt.value:>2}  {opt.name}{mark}")
    return "\n".join(out)


@mcp.tool()
def redis_use_server(s: int) -> str:
    """Switch all subsequent operations to another Redis server (id from redis_servers).

    Note: the db each server id maps to is fixed in phpRedisAdmin's server-side
    config; there is deliberately no db parameter.
    """
    client = get_client()
    sid = str(s)
    r = client.get("index.php", params={"s": sid}, timeout=30)
    r.raise_for_status()
    select = find_server_select(r.text)
    name = sid
    dead = ""
    if select:
        for opt in parse_server_options(select):
            if opt.value == sid:
                name = opt.name
    if "Can't connect to this server" in r.text:
        dead = "  [WARNING: can't connect to this server]"
    client.server_id = sid
    return f"switched to s={sid} '{name}'{dead}"
