"""The single MCPServer instance.

Tool modules import ``mcp`` from here to register themselves; the entry
point imports it to run. Keeping the instance in its own module avoids
circular imports between the server object and the tools.

This is also where the server *identifies itself*: hosts surface ``instructions``
to the AI (opencode >= 1.17.10 puts them in the session context), and tool
docstrings carry ``ONLY_PATH`` so the jurisdiction claim survives even where
instructions are dropped.
"""

from inspect import cleandoc

from mcp.server import MCPServer

# The one-sentence jurisdiction claim, appended to tool docstrings by
# identity_tool (below). It exists because the AI holding these tools usually
# also holds a shell: without this, "look at Redis" drifts to redis-cli /
# config-file hunting, none of which can work when the port is not exposed.
ONLY_PATH = (
    "Redis here is reachable only through this phpRedisAdmin MCP server "
    "(no exposed port: redis-cli, redis-py or direct TCP connections will "
    "not work)."
)


def identity_tool(fn):
    """``@mcp.tool()`` plus the ONLY_PATH jurisdiction claim.

    Appended *after* the function's own docstring (so the first line stays the
    tool's purpose) and registered while ``fn.__doc__`` is still a plain
    literal — an f-string docstring compiles to ``BUILD_STRING`` and leaves
    ``__doc__`` None, which silently blanks every tool description.
    """
    if fn.__doc__:
        fn.__doc__ = f"{cleandoc(fn.__doc__).rstrip()}\n\n{ONLY_PATH}"
    return mcp.tool()(fn)


mcp = MCPServer(
    "phpredisadmin",
    title="Redis via phpRedisAdmin",
    description=(
        "Read/write Redis through a phpRedisAdmin web UI — the only Redis "
        "access path in this environment."
    ),
    instructions=(
        "Operate Redis through the phpRedisAdmin web UI.\n"
        "\n"
        f"Identity: {ONLY_PATH} Do not go looking for Redis connection configs\n"
        "or credentials on disk — every Redis task (read, write, delete, TTL,\n"
        "inspect) goes through these tools.\n"
        "\n"
        "Workflow:\n"
        "1. redis_servers() — list the configured instances; each s= entry is one\n"
        "   db (their db mapping is fixed server-side, there is no db parameter).\n"
        "2. redis_use_server(s) — switch to the right db before touching keys.\n"
        "3. redis_keys(filter) — find keys. A specific filter (prefix substring or\n"
        "   glob like 'user:*') is mandatory; full-keyspace scans are refused and\n"
        "   listings are capped (200 keys; export 50).\n"
        "4. redis_get / redis_export / redis_set / redis_delete / redis_ttl —\n"
        "   operate on keys.\n"
        "\n"
        "Caveats (verified live on the target instance):\n"
        "- Writes are validated locally: a FAILED return with a reason means the\n"
        "  old phpRedisAdmin would otherwise silently drop the write (fake OK).\n"
        "- Setting a positive TTL fails on very old Predis installs; seconds=-1\n"
        "  (persist) works everywhere.\n"
        "- Key filtering is client-side (the instance ignores the server filter\n"
        "  param), so listings still fetch the full key page — keep filters tight.\n"
    ),
)
