"""Data query server over DuckDB. SELECT-only, allowlisted tables, row cap, read-only connection."""
from __future__ import annotations

import os

import duckdb
import sqlglot
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from sqlglot import exp

from .governance import audit, run

ALLOWED = {"orders", "customers"}
MAX_ROWS = 500


def _con() -> duckdb.DuckDBPyConnection:
    path = os.getenv("MCP_DUCKDB", "")
    if path:
        return duckdb.connect(path, read_only=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE customers AS SELECT i AS customer_id, 'Customer ' || i AS name, ['North','South','East','West'][1 + i % 4] AS region FROM range(1, 51) t(i)")
    con.execute("CREATE TABLE orders AS SELECT i AS order_id, 1 + i % 50 AS customer_id, round(100 + (i * 37) % 900, 2) AS amount, DATE '2026-01-01' + CAST(i % 270 AS INT) AS order_date FROM range(1, 1001) t(i)")
    con.execute("CREATE TABLE payroll AS SELECT 1 AS emp, 100000 AS salary")  # present but not allowlisted
    return con


CON = _con()


def check_sql(sql: str) -> str:
    stmts = sqlglot.parse(sql, read="duckdb")
    if len(stmts) != 1 or not isinstance(stmts[0], (exp.Select, exp.Union)):
        raise ValueError("only a single SELECT statement is allowed")
    tree = stmts[0]
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    bad = {t.name for t in tree.find_all(exp.Table)} - ctes - ALLOWED
    if bad:
        raise ValueError(f"tables not allowed: {sorted(bad)}")
    if tree.find(exp.Anonymous) and any(f.name.lower().startswith(("read_", "glob")) for f in tree.find_all(exp.Anonymous)):
        raise ValueError("file-access functions are not allowed")
    return tree.limit(min(int(tree.args["limit"].expression.name), MAX_ROWS) if tree.args.get("limit") else MAX_ROWS).sql("duckdb")


@audit("data", "data:read")
def list_tables() -> dict[str, list[str]]:
    return {t: [r[0] for r in CON.execute(f"DESCRIBE {t}").fetchall()] for t in sorted(ALLOWED)}


@audit("data", "data:read")
def run_query(sql: str) -> dict:
    if len(sql) > 5000:
        raise ValueError("query too long")
    safe = check_sql(sql)
    cur = CON.execute(safe)
    return {"sql": safe, "columns": [d[0] for d in cur.description], "rows": [list(map(str, r)) for r in cur.fetchall()]}


def build() -> MCPServer:
    srv = MCPServer("data", instructions="Read-only analytics over allowlisted tables. Call list_tables first.")
    for f in (list_tables, run_query):
        srv.tool(annotations=ToolAnnotations(readOnlyHint=True))(f)
    return srv


def main() -> None:
    run(build())

if __name__ == "__main__":
    main()
