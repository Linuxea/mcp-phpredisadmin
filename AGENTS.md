# AGENTS.md

MCP server (stdio) that operates Redis through a phpRedisAdmin web UI — it scrapes HTML pages, not a Redis protocol connection. Tested against an old phpRedisAdmin at `http://redis.chathot.me` (16 selector entries, no login — all 16 entries point to **one** Redis process, each pinned to a different db; see quirks below).

## Commands

```bash
uv sync                                              # install (creates .venv)
uv run pra-mcp                                       # run the server (needs PRA_URL)
uv run pytest                                        # offline tests only (live tests skip silently!)
PRA_LIVE=1 PRA_URL=http://redis.chathot.me uv run pytest   # full suite incl. live
PRA_LIVE=1 PRA_URL=... uv run pytest tests/test_tools_live.py::TestZSet -v  # one class/test
```

Live tests are opt-in via **two** env vars (`PRA_LIVE` + `PRA_URL`) so a production `PRA_URL` in the shell never gets hit by accident. If pytest reports skips for `test_tools_live.py`, that's why.

## Architecture

- `src/pra_mcp/registry.py` holds the single `MCPServer` instance; tool modules under `tools/` import `mcp` from it and decorate — **importing a tools module is what registers its tools** (wired in `tools/__init__.py` and `__init__.py`).
- `http_client.py` owns the requests session, auth/CSRF, and current server/db as **instance state** (`get_client()` lazy singleton, `reset_client()` for tests). No module-level mutable globals.
- `parsing.py` is pure functions over HTML fixture strings — extend it rather than putting regexes in tools.
- MCP Python SDK is **v2**: `from mcp.server import MCPServer` (v1's `fastmcp.FastMCP` import is gone). In tests, `Client(mcp)` connects in memory; `list_tools()` returns a `ListToolsResult` — the tools are on `.tools`.

## Testing philosophy — read before editing tests

- Live tests pin **actual server behaviour**, including bugs. `TestKnownIssues` / `TestValidation` cases assert current (sometimes wrong-looking) behaviour on purpose. When fixing a tool, flip the pinned assertion to the desired behaviour first (red), then fix the tool (green), and move the case into its type class.
- Live tests write only under the `mcp:test:` prefix and a module fixture deletes those keys afterwards. Never widen that prefix, never add flush/dangerous ops, and keep `redis_export`/`redis_keys` refusal tests intact.
- `redis_keys`/`redis_export` **require a filter** and refuse `*`/``/`**` — full-keyspace scans are banned by design (LLM-callable surface). Don't "fix" the refusal.
- The live instance is shared and busy: index.php renders ~4.7k keys, so page-heavy calls are slow and occasionally truncated (see the retry in `test_servers_lists_all_instances`). A one-off flake there is infrastructure, not a code bug.

## Server quirks (all verified live, pinned in tests)

- edit.php/delete.php render a success page even when branch conditions don't match → the tool layer validates parameters locally before POSTing. Any new write path needs the same guard.
- `redis_set` with `type="list"` must always send the `index` field (edit.php requires `isset($_POST['index'])`); omitting it was a silent no-op reporting OK.
- list `index=-1` is **append** on this old instance (upstream master documents prepend).
- Positive TTLs die server-side (`Predis SETTIMEOUT` Fatal error on this instance); `redis_ttl(-1)` persist works. The PHP Fatal error must surface as `FAILED`, never raw HTML.
- The instance ignores the GET `filter` param — all key filtering is client-side (`_matches`: glob chars → fnmatch, else substring). `ttl.php` needs `key` in the POST body, not the query string.
- The instance also ignores the GET `d` (db) param: every `s=` entry is pinned to the db configured in phpRedisAdmin's server list. Verified 2026-10-19 via process fingerprints (info.php: same `process_id`/`run_id`/port 2722 for all 16 entries) — one Redis process, entries map s→db as: s0→db0 starchat, s1→db1 starchat_rank, s2→db5 video_chat, s3→db2 starchat_lite, s4→db4 waga, s5→db6 farah, s6→db7 salam-ai, s7→db8 kalam, s8→db9 gama, s9→db11 najmat, s10→db12 sawtik, s11→db13 drama, s12→db14 reelstar, s13→db15 mela, s14→db16 T_project, s15→db17 tawla (db10/db18 exist but have no entry). `PRA_DB`, the client's db state, and `redis_use_server`'s db param were therefore **removed** (2026-10-19); `qs()` no longer sends `d`. Pick the right `s` instead.

## Ops notes

- opencode entry: `["uv", "run", "--project", "<repo>", "pra-mcp"]` with env `PRA_URL`, `PRA_SERVER_ID`. There is no auth on the test instance; `PRA_LOGIN=form` flow exists but is untested live.
- README carries the user-facing tool list and known-limitation table — update it together with tool behaviour changes.
