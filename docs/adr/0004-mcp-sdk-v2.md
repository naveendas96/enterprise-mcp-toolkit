# ADR 0004: Official `mcp` Python SDK v2 (`MCPServer`)
**Decision:** Pin `mcp>=2.3,<3`, using `MCPServer` (the v2 name for FastMCP). Use stdio for desktop clients and streamable HTTP (`--http`) for containers.
**Consequences:** v1 examples on the internet use `FastMCP`. The code is otherwise the same in shape.
