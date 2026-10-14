"""Spawn each server over stdio (exactly as Claude Desktop / Cursor do) and call a tool."""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CALLS = [("emcp.itsm", "search_tickets", {"query": "payroll"}),
         ("emcp.data", "run_query", {"sql": "SELECT c.region, round(sum(o.amount),2) AS revenue FROM orders o JOIN customers c USING (customer_id) GROUP BY 1 ORDER BY 1"}),
         ("emcp.data", "run_query", {"sql": "DELETE FROM orders"}),
         ("emcp.docs", "search_docs", {"query": "vpn disconnects"})]


async def call(mod: str, tool: str, args: dict) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", mod], env={**os.environ, "MCP_ACTOR": "demo"})
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [t.name for t in (await s.list_tools()).tools]
        res = await s.call_tool(tool, args)
        text = " ".join(getattr(c, "text", "") for c in res.content)[:300]
        print(f"[{mod}] tools={tools}\n  {tool}({args}) -> error={res.is_error if hasattr(res, 'is_error') else res.isError}\n  {text}\n")


async def main() -> None:
    for c in CALLS:
        await call(*c)

asyncio.run(main())
