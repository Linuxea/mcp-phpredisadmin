#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "requests>=2.28"]
# ///
import os
import re
import html as html_mod
import json
from urllib.parse import unquote

import requests
from mcp.server.fastmcp import FastMCP

PRA_URL = os.environ.get("PRA_URL", "").rstrip("/")
PRA_USER = os.environ.get("PRA_USER", "")
PRA_PASS = os.environ.get("PRA_PASS", "")
PRA_LOGIN = os.environ.get("PRA_LOGIN", "basic")

mcp = FastMCP("phpredisadmin")

session = requests.Session()
session.headers["User-Agent"] = "mcp-phpredisadmin/1.0"
_csrf = None
_server_id = os.environ.get("PRA_SERVER_ID", "0")
_db = os.environ.get("PRA_DB", "0")
_current_server_name = ""


def _qs():
    return {"s": _server_id, "d": _db}


def _login_form():
    r = session.post(
        f"{PRA_URL}/login.php",
        data={"username": PRA_USER, "password": PRA_PASS},
        timeout=15,
        allow_redirects=True,
    )
    if "login.php" in r.url and r.status_code == 200:
        if 'name="csrf"' not in r.text:
            raise RuntimeError("form login failed: still on login page")


def _ensure_auth_and_csrf():
    global _csrf
    if PRA_USER and PRA_LOGIN == "form":
        _login_form()
    r = session.get(f"{PRA_URL}/edit.php", params=_qs(), timeout=15)
    if r.status_code == 401:
        raise RuntimeError(
            "HTTP auth failed (401). Check PRA_USER/PRA_PASS or set PRA_LOGIN=form."
        )
    if "login.php" in r.url and 'name="csrf"' not in r.text:
        raise RuntimeError("login required: set PRA_USER/PRA_PASS and PRA_LOGIN=form")
    m = re.search(r'name="csrf"\s+value="([^"]+)"', r.text)
    _csrf = m.group(1) if m else ""


def _csrf_token():
    if _csrf is None:
        _ensure_auth_and_csrf()
    return _csrf


def _post(path, params=None, data=None):
    data = dict(data or {})
    token = _csrf_token()
    if token:
        data["csrf"] = token
    r = session.post(
        f"{PRA_URL}/{path}", params=params or _qs(), data=data, timeout=60
    )
    r.raise_for_status()
    return r


def _strip_html(text):
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html_mod.unescape(text)).strip()


@mcp.tool()
def redis_keys(filter: str = "") -> str:
    """List Redis keys (optionally filtered by substring) without fetching values."""
    params = _qs()
    if filter:
        params["filter"] = filter
    r = session.get(f"{PRA_URL}/index.php", params=params, timeout=60)
    r.raise_for_status()
    keys = set()
    for m in re.finditer(r'[?&;]key=([^"&#]+)', r.text):
        k = unquote(m.group(1))
        if not filter or filter.lower() in k.lower():
            keys.add(k)
    if not keys:
        return "no keys found (or page requires login — run redis_info to check auth)"
    return json.dumps(sorted(keys), ensure_ascii=False, indent=1)


@mcp.tool()
def redis_get(key: str) -> str:
    """Get the full value of a Redis key as JSON. Works for string/hash/list/set/zset."""
    r = _post("export.php", params={**_qs(), "key": key}, data={"type": "json"})
    return r.text


@mcp.tool()
def redis_export(filter: str = "") -> str:
    """Dump all keys (optionally filtered by substring) with values as one JSON object. Heavy: use sparingly."""
    data = {"type": "json"}
    if filter:
        data["filter"] = filter
    r = _post("export.php", data=data)
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
    data = {"type": type, "key": key, "value": value}
    if hkey:
        data["hkey"] = hkey
    if index != "":
        data["index"] = index
    if score != "":
        data["score"] = score
    r = _post("edit.php", data=data)
    if "exception" in r.text or "ERROR" in r.text:
        return f"FAILED: {_strip_html(r.text)[:500]}"
    return f"OK: {type} key '{key}' saved"


@mcp.tool()
def redis_delete(key: str) -> str:
    """Delete a Redis key."""
    r = _post("delete.php", params={**_qs(), "key": key}, data={"post": "1"})
    return f"OK: '{key}' deleted" if "?view" in r.text else f"Response: {r.text[:200]}"


@mcp.tool()
def redis_info() -> str:
    """Redis server info (version, memory, clients, keyspace) via phpRedisAdmin."""
    r = session.get(f"{PRA_URL}/info.php", params=_qs(), timeout=30)
    r.raise_for_status()
    return _strip_html(r.text)[:4000]


@mcp.tool()
def redis_servers() -> str:
    """List all Redis servers configured in phpRedisAdmin, marking the current one."""
    r = session.get(f"{PRA_URL}/index.php", params={"s": _server_id, "d": _db}, timeout=30)
    r.raise_for_status()
    m = re.search(r'<select id="server">(.*?)</select>', r.text, flags=re.S)
    if not m:
        return "no server selector found (single-server setup or old version); current s=" + _server_id
    out = []
    for opt in re.finditer(r'<option value="(\d+)"\s*(selected="selected")?\s*>([^<]+)</option>', m.group(1)):
        sid, sel, name = opt.group(1), opt.group(2), html_mod.unescape(opt.group(3)).strip()
        mark = "  <- current" if sel or sid == _server_id else ""
        out.append(f"s={sid:>2}  {name}{mark}")
    return "\n".join(out)


@mcp.tool()
def redis_use_server(s: int, db: int = 0) -> str:
    """Switch all subsequent operations to another Redis server (id from redis_servers) and optional db."""
    global _server_id, _db
    sid = str(s)
    r = session.get(f"{PRA_URL}/index.php", params={"s": sid, "d": db}, timeout=30)
    r.raise_for_status()
    m = re.search(r'<select id="server">(.*?)</select>', r.text, flags=re.S)
    name = sid
    dead = ""
    if m:
        for opt in re.finditer(r'<option value="(\d+)"[^>]*>([^<]+)</option>', m.group(1)):
            if opt.group(1) == sid:
                name = html_mod.unescape(opt.group(2)).strip()
    if "Can't connect to this server" in r.text:
        dead = "  [WARNING: can't connect to this server]"
    _server_id, _db = sid, str(db)
    return f"switched to s={sid} (db={db}) '{name}'{dead}"


if __name__ == "__main__":
    if not PRA_URL:
        raise SystemExit("PRA_URL env var is required, e.g. https://pra.example.com")
    mcp.run()
