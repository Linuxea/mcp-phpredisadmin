"""The single MCPServer instance.

Tool modules import ``mcp`` from here to register themselves; the entry
point imports it to run. Keeping the instance in its own module avoids
circular imports between the server object and the tools.
"""

from mcp.server import MCPServer

mcp = MCPServer("phpredisadmin")
