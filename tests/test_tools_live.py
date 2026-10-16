"""Live integration tests against a real phpRedisAdmin instance.

Run (double opt-in so a production PRA_URL is never hit by accident):

    PRA_LIVE=1 PRA_URL=http://redis.chathot.me uv run pytest tests/test_tools_live.py -v

All writes go to the ``mcp:test:`` namespace and are removed by a module-scoped
fixture afterwards. Only safe operations are used — no flush, no deletion of
foreign keys, no full export (it times out on this instance, see TestExport).

Behaviours marked KNOWN ISSUE were verified live on 2026-10-16 against the old
phpRedisAdmin at redis.chathot.me (no csrf, GET filter ignored server-side).
They pin *current* behaviour: when a fix lands, update these deliberately.
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not (os.environ.get("PRA_URL") and os.environ.get("PRA_LIVE")),
        reason="set PRA_LIVE=1 and PRA_URL to run live tests",
    ),
]

KEY_PREFIX = "mcp:test:"


def NS(name: str) -> str:
    return KEY_PREFIX + name


async def call(mcp_client, tool: str, args: dict) -> str:
    result = await mcp_client.call_tool(tool, args)
    return result.content[0].text


async def get_value(mcp_client, key: str):
    """redis_get + json.loads; returns ('null'-literal sentinel as None)."""
    text = await call(mcp_client, "redis_get", {"key": key})
    if text == "null":
        return None
    return json.loads(text)


@pytest.fixture(autouse=True)
def _isolate():
    """Drop the shared client around each test so a failed server switch
    cannot leak s=/db= state into the next case (cheap: one extra GET)."""
    from pra_mcp.http_client import reset_client

    reset_client()
    yield
    reset_client()


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    """Remove every mcp:test:* key after the module finished.

    Uses the plain Python tool functions (no MCP hop) since the in-memory
    client fixture is function-scoped.
    """
    from pra_mcp.http_client import reset_client
    from pra_mcp.tools.keys import redis_keys
    from pra_mcp.tools.kv import redis_delete

    reset_client()
    yield
    try:
        listing = redis_keys(filter=KEY_PREFIX)
        keys = json.loads(listing) if listing.startswith("[") else []
        for k in keys:
            try:
                redis_delete(k)
            except Exception as exc:  # pragma: no cover - best effort
                print(f"cleanup: failed to delete {k}: {exc}")
    finally:
        reset_client()


# --------------------------------------------------------------------------
# string
# --------------------------------------------------------------------------
class TestString:
    async def test_roundtrip(self, mcp_client):
        r = await call(mcp_client, "redis_set", {"key": NS("str"), "value": "hello"})
        assert r.startswith("OK:")
        assert await get_value(mcp_client, NS("str")) == "hello"

    async def test_overwrite(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("str_ow"), "value": "v1"})
        await call(mcp_client, "redis_set", {"key": NS("str_ow"), "value": "v2"})
        assert await get_value(mcp_client, NS("str_ow")) == "v2"

    async def test_unicode_and_emoji(self, mcp_client):
        val = "中文值🎉 café"
        await call(mcp_client, "redis_set", {"key": NS("str_uni"), "value": val})
        assert await get_value(mcp_client, NS("str_uni")) == val

    async def test_newline_quotes_entities(self, mcp_client):
        val = 'line1\nline2 "q" &amp; <b>'
        await call(mcp_client, "redis_set", {"key": NS("str_sp"), "value": val})
        assert await get_value(mcp_client, NS("str_sp")) == val

    async def test_json_string_value_stays_string(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("str_js"), "value": '{"a":1}'})
        # export wraps it as a JSON string, so it round-trips as text
        assert await get_value(mcp_client, NS("str_js")) == '{"a":1}'

    async def test_empty_value(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("str_empty"), "value": ""})
        assert await get_value(mcp_client, NS("str_empty")) == ""

    async def test_numeric_string(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("str_num"), "value": "42"})
        assert await get_value(mcp_client, NS("str_num")) == "42"

    async def test_long_value_10k(self, mcp_client):
        val = "x" * 10_000
        await call(mcp_client, "redis_set", {"key": NS("str_long"), "value": val})
        assert await get_value(mcp_client, NS("str_long")) == val


# --------------------------------------------------------------------------
# hash
# --------------------------------------------------------------------------
class TestHash:
    async def test_two_fields(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("h"), "value": "v1", "type": "hash", "hkey": "f1"})
        await call(mcp_client, "redis_set", {"key": NS("h"), "value": "v2", "type": "hash", "hkey": "f2"})
        assert await get_value(mcp_client, NS("h")) == {"f1": "v1", "f2": "v2"}

    async def test_field_overwrite(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("h_ow"), "value": "old", "type": "hash", "hkey": "f"})
        await call(mcp_client, "redis_set", {"key": NS("h_ow"), "value": "new", "type": "hash", "hkey": "f"})
        assert await get_value(mcp_client, NS("h_ow")) == {"f": "new"}

    async def test_unicode_field_and_value(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("h_uni"), "value": "值", "type": "hash", "hkey": "字段"})
        assert await get_value(mcp_client, NS("h_uni")) == {"字段": "值"}

    async def test_hash_without_hkey_is_rejected_locally(self, mcp_client):
        """FIXED (was a fake OK): the tool validates before hitting the server."""
        r = await call(mcp_client, "redis_set", {"key": NS("h_rej"), "value": "v", "type": "hash"})
        assert r.startswith("FAILED:")
        assert "hkey" in r
        assert await call(mcp_client, "redis_get", {"key": NS("h_rej")}) == "null"

    async def test_hash_requires_hkey_to_have_any_effect(self, mcp_client):
        # Sanity anchor for the KNOWN ISSUE test below: with hkey it works.
        await call(mcp_client, "redis_set", {"key": NS("h_ok"), "value": "v", "type": "hash", "hkey": "f"})
        assert await get_value(mcp_client, NS("h_ok")) == {"f": "v"}


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------
class TestList:
    async def test_append_with_default_index_now_writes(self, mcp_client):
        """FIXED (was a silent no-op reporting OK): the tool now always sends
        the index field for lists; edit.php treats an explicit '' as rPush."""
        r = await call(mcp_client, "redis_set", {"key": NS("l_app"), "value": "a", "type": "list"})
        assert r.startswith("OK:")
        r = await call(mcp_client, "redis_set", {"key": NS("l_app"), "value": "b", "type": "list"})
        assert r.startswith("OK:")
        assert await get_value(mcp_client, NS("l_app")) == ["a", "b"]

    async def test_prepend_creates_list(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("l"), "value": "p", "type": "list", "index": "-1"})
        assert await get_value(mcp_client, NS("l")) == ["p"]

    async def test_index_minus_one_appends_on_this_instance(self, mcp_client):
        """QUIRK (verified live): upstream phpRedisAdmin documents index=-1 as
        lPush/prepend, but this old deployment APPENDS instead — two -1 writes
        land in write order. The tool docstring's 'prepend' claim is wrong
        against instances like this one."""
        await call(mcp_client, "redis_set", {"key": NS("l2"), "value": "a", "type": "list", "index": "-1"})
        await call(mcp_client, "redis_set", {"key": NS("l2"), "value": "b", "type": "list", "index": "-1"})
        assert await get_value(mcp_client, NS("l2")) == ["a", "b"]

    async def test_index_overwrite(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("l3"), "value": "a", "type": "list", "index": "-1"})
        await call(mcp_client, "redis_set", {"key": NS("l3"), "value": "b", "type": "list", "index": "-1"})
        await call(mcp_client, "redis_set", {"key": NS("l3"), "value": "X", "type": "list", "index": "0"})
        assert await get_value(mcp_client, NS("l3")) == ["X", "b"]

    async def test_index_equal_to_size_appends(self, mcp_client):
        # edit.php treats index == len as rPush
        await call(mcp_client, "redis_set", {"key": NS("l4"), "value": "p", "type": "list", "index": "-1"})
        await call(mcp_client, "redis_set", {"key": NS("l4"), "value": "q", "type": "list", "index": "1"})
        assert await get_value(mcp_client, NS("l4")) == ["p", "q"]

    async def test_index_out_of_bounds_fails(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("l5"), "value": "p", "type": "list", "index": "-1"})
        r = await call(mcp_client, "redis_set", {"key": NS("l5"), "value": "z", "type": "list", "index": "99"})
        assert r.startswith("FAILED:")
        # list unchanged
        assert await get_value(mcp_client, NS("l5")) == ["p"]


# --------------------------------------------------------------------------
# set
# --------------------------------------------------------------------------
class TestSet:
    async def test_members_and_dedup(self, mcp_client):
        for v in ("x", "y", "x"):
            await call(mcp_client, "redis_set", {"key": NS("s"), "value": v, "type": "set"})
        assert sorted(await get_value(mcp_client, NS("s"))) == ["x", "y"]

    async def test_unicode_member(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("s_uni"), "value": "成员", "type": "set"})
        assert await get_value(mcp_client, NS("s_uni")) == ["成员"]


# --------------------------------------------------------------------------
# zset
# --------------------------------------------------------------------------
class TestZSet:
    async def test_members_ordered_by_score(self, mcp_client):
        for member, score in (("m30", "30"), ("m10", "10"), ("m20", "20")):
            await call(
                mcp_client,
                "redis_set",
                {"key": NS("z"), "value": member, "type": "zset", "score": score},
            )
        assert await get_value(mcp_client, NS("z")) == ["m10", "m20", "m30"]

    async def test_export_omits_scores(self, mcp_client):
        """KNOWN LIMITATION (verified): export.php zRange() output has no scores."""
        await call(mcp_client, "redis_set", {"key": NS("z_sc"), "value": "a", "type": "zset", "score": "1.5"})
        raw = await call(mcp_client, "redis_get", {"key": NS("z_sc")})
        assert json.loads(raw) == ["a"]  # plain member list, no score anywhere

    async def test_score_ordering_after_member_overwrite(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("z_ow"), "value": "m", "type": "zset", "score": "5"})
        await call(mcp_client, "redis_set", {"key": NS("z_ow"), "value": "n", "type": "zset", "score": "1"})
        assert await get_value(mcp_client, NS("z_ow")) == ["n", "m"]

    async def test_zset_without_score_is_rejected_locally(self, mcp_client):
        """FIXED (was a fake OK): the tool validates before hitting the server."""
        r = await call(mcp_client, "redis_set", {"key": NS("z_rej"), "value": "m", "type": "zset"})
        assert r.startswith("FAILED:")
        assert "score" in r
        assert await call(mcp_client, "redis_get", {"key": NS("z_rej")}) == "null"

    async def test_negative_and_float_scores(self, mcp_client):
        for member, score in (("neg", "-3.5"), ("zero", "0"), ("big", "100")):
            await call(mcp_client, "redis_set", {"key": NS("z_f"), "value": member, "type": "zset", "score": score})
        assert await get_value(mcp_client, NS("z_f")) == ["neg", "zero", "big"]


# --------------------------------------------------------------------------
# local validation (fixed 2026-10-17; was the fake-OK family)
# --------------------------------------------------------------------------
class TestValidation:
    async def test_bogus_type_is_rejected_locally(self, mcp_client):
        r = await call(mcp_client, "redis_set", {"key": NS("val_bogus"), "value": "x", "type": "bogus"})
        assert r.startswith("FAILED:")
        assert "unknown type" in r
        assert await call(mcp_client, "redis_get", {"key": NS("val_bogus")}) == "null"

    async def test_zset_non_numeric_score_is_rejected_locally(self, mcp_client):
        r = await call(mcp_client, "redis_set", {"key": NS("val_zb"), "value": "m", "type": "zset", "score": "abc"})
        assert r.startswith("FAILED:")
        assert "numeric" in r
        assert await call(mcp_client, "redis_get", {"key": NS("val_zb")}) == "null"


# --------------------------------------------------------------------------
# KNOWN ISSUES still open — pinned; fix should flip these deliberately.
# --------------------------------------------------------------------------
class TestKnownIssues:
    async def test_delete_missing_key_still_reports_ok(self, mcp_client):
        r = await call(mcp_client, "redis_delete", {"key": NS("ki_ghost")})
        assert r.startswith("OK:")  # indistinguishable from a real deletion

    async def test_get_missing_key_returns_null_literal(self, mcp_client):
        # A stored JSON null would look identical — acceptable, documented.
        assert await call(mcp_client, "redis_get", {"key": NS("ki_ghost2")}) == "null"


# --------------------------------------------------------------------------
# keys & filter semantics
# --------------------------------------------------------------------------
class TestKeysFilter:
    async def test_keys_finds_created_keys(self, mcp_client):
        await call(mcp_client, "redis_set", {"key": NS("k1"), "value": "1"})
        await call(mcp_client, "redis_set", {"key": NS("k2"), "value": "2"})
        listing = await call(mcp_client, "redis_keys", {"filter": "mcp:test:k"})
        keys = json.loads(listing)
        assert NS("k1") in keys and NS("k2") in keys

    async def test_keys_filter_no_match(self, mcp_client):
        listing = await call(mcp_client, "redis_keys", {"filter": "zzz_mcp_no_such_thing"})
        assert listing.startswith("no keys found")

    async def test_keys_midstring_filter_matches(self, mcp_client):
        """Server ignores the GET filter param (old phpRedisAdmin), so filtering
        is the client-side substring check — mid-string patterns do match."""
        await call(mcp_client, "redis_set", {"key": NS("mid:foo"), "value": "v"})
        listing = await call(mcp_client, "redis_keys", {"filter": "test:mid"})
        assert NS("mid:foo") in json.loads(listing)

    async def test_keys_glob_filter_matches_nothing(self, mcp_client):
        """KNOWN QUIRK: a glob like 'mcp:test:*' passes server-side untouched,
        then fails the client-side substring check ('*' is not a substring)."""
        await call(mcp_client, "redis_set", {"key": NS("glob"), "value": "v"})
        listing = await call(mcp_client, "redis_keys", {"filter": "mcp:test:glob*"})
        assert listing.startswith("no keys found")

    async def test_keys_unfiltered_contains_existing_keys(self, mcp_client):
        """No-filter listing returns the whole keyspace (4761+ keys here)."""
        await call(mcp_client, "redis_set", {"key": NS("all"), "value": "v"})
        listing = await call(mcp_client, "redis_keys", {})
        assert NS("all") in json.loads(listing)


# --------------------------------------------------------------------------
# delete
# --------------------------------------------------------------------------
class TestDelete:
    async def test_set_delete_get_roundtrip(self, mcp_client):
        key = NS("del")
        await call(mcp_client, "redis_set", {"key": key, "value": "bye"})
        assert await get_value(mcp_client, key) == "bye"
        r = await call(mcp_client, "redis_delete", {"key": key})
        assert r.startswith("OK:")
        assert await call(mcp_client, "redis_get", {"key": key}) == "null"

    async def test_deleted_key_leaves_keys_listing(self, mcp_client):
        key = NS("del2")
        await call(mcp_client, "redis_set", {"key": key, "value": "x"})
        await call(mcp_client, "redis_delete", {"key": key})
        listing = await call(mcp_client, "redis_keys", {"filter": "mcp:test:del2"})
        if listing.startswith("["):
            assert key not in json.loads(listing)


# --------------------------------------------------------------------------
# servers & switching
# --------------------------------------------------------------------------
class TestServers:
    async def test_servers_lists_all_instances(self, mcp_client):
        """FLAKY-PRONE: index.php renders the whole 4.7k-key sidebar, and under
        load the page sometimes comes back truncated so the selector cannot be
        parsed. Retry once on that specific symptom only."""
        listing = await call(mcp_client, "redis_servers", {})
        if "no server selector found" in listing:
            listing = await call(mcp_client, "redis_servers", {})
        # this instance exposes 16 servers; starchat is s=0, gama is s=8
        assert "starchat" in listing, f"listing was: {listing[:200]}"
        assert "gama" in listing, f"listing was: {listing[:200]}"
        assert "<- current" in listing, f"listing was: {listing[:200]}"

    async def test_use_server_switch_and_back(self, mcp_client):
        r = await call(mcp_client, "redis_use_server", {"s": 1})
        assert r.startswith("switched to s=1")
        # reads work on the other instance (info only — we write nothing there)
        info = await call(mcp_client, "redis_info", {})
        assert "redis" in info.lower()
        back = await call(mcp_client, "redis_use_server", {"s": 0})
        assert back.startswith("switched to s=0")
        # s=0 serves keys again
        listing = await call(mcp_client, "redis_keys", {"filter": "mcp:test:"})
        assert listing

    async def test_use_server_marks_dead_servers(self, mcp_client):
        """If an instance is down phpRedisAdmin renders 'Can't connect' — the
        tool surfaces it as a WARNING suffix. Cannot force a dead server here,
        so only assert the happy path keeps the suffix empty."""
        r = await call(mcp_client, "redis_use_server", {"s": 0})
        assert "WARNING" not in r


# --------------------------------------------------------------------------
# info
# --------------------------------------------------------------------------
class TestInfo:
    async def test_info_mentions_redis(self, mcp_client):
        info = await call(mcp_client, "redis_info", {})
        assert "redis" in info.lower()

    async def test_info_is_bounded(self, mcp_client):
        info = await call(mcp_client, "redis_info", {})
        assert len(info) <= 4000


# --------------------------------------------------------------------------
# MCP surface (schema-level, no Redis interaction)
# --------------------------------------------------------------------------
class TestToolSchemas:
    async def test_all_tools_advertised(self, mcp_client):
        result = await mcp_client.list_tools()
        names = {t.name for t in result.tools}
        assert {
            "redis_info",
            "redis_keys",
            "redis_get",
            "redis_set",
            "redis_delete",
            "redis_export",
            "redis_servers",
            "redis_use_server",
        } <= names

    async def test_redis_set_schema_requires_key_and_value(self, mcp_client):
        result = await mcp_client.list_tools()
        by_name = {t.name: t for t in result.tools}
        schema = by_name["redis_set"].input_schema
        assert set(schema["required"]) == {"key", "value"}
        assert set(schema["properties"]) >= {"key", "value", "type", "hkey", "index", "score"}

    async def test_every_tool_has_description(self, mcp_client):
        result = await mcp_client.list_tools()
        for t in result.tools:
            assert t.description and t.description.strip(), f"{t.name} lacks a description"


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
class TestExport:
    async def test_full_export_times_out_on_large_keyspace(self, mcp_client):
        """SKIPPED by design: verified manually on 2026-10-16 that export.php
        runs KEYS('*') over the whole keyspace and does not answer within 30s
        here (~5k keys). Do not run it from the suite; it hammers the Redis.
        If a fix lands (paged export / SCAN), replace this with a real test."""
        pytest.skip("full export times out on this instance; see docstring")

