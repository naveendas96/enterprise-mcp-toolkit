import asyncio
import json
import os

import pytest

from emcp import data, docs, itsm
from emcp.governance import PermissionDenied


def tool_names(srv):
    return {t.name for t in asyncio.run(srv.list_tools())}


def test_read_only_by_default_hides_write_tools():
    assert tool_names(itsm.build()) == {"get_ticket", "search_tickets"}


def test_write_scope_registers_write_tools(monkeypatch):
    monkeypatch.setenv("MCP_SCOPES", "itsm:read,itsm:write")
    assert {"create_ticket", "update_ticket_state"} <= tool_names(itsm.build())


def test_write_blocked_without_scope_even_if_called_directly():
    with pytest.raises(PermissionDenied):
        itsm.create_ticket(title="Printer on fire", description="x", priority="P3")


def test_create_and_transition(monkeypatch):
    monkeypatch.setenv("MCP_SCOPES", "itsm:read,itsm:write")
    t = itsm.create_ticket(title="Printer jammed on floor 3", description="paper", priority="P3")
    assert itsm.update_ticket_state(ticket_id=t["id"], new_state="in_progress")["state"] == "in_progress"
    with pytest.raises(ValueError):
        itsm.update_ticket_state(ticket_id=t["id"], new_state="new")


def test_input_validation_via_mcp_protocol(monkeypatch):
    monkeypatch.setenv("MCP_SCOPES", "itsm:read,itsm:write")
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="P1"):
        asyncio.run(itsm.build().call_tool("create_ticket", {"title": "Hi", "description": "x", "priority": "P9"}))


def test_search_tickets_via_protocol():
    r = asyncio.run(itsm.build().call_tool("search_tickets", {"query": "vpn"}))
    assert "INC0001" in json.dumps(r.model_dump(), default=str)


@pytest.mark.parametrize("sql", ["DROP TABLE orders", "SELECT * FROM payroll", "SELECT 1; SELECT 2",
                                 "SELECT * FROM read_csv('/etc/passwd')", "INSERT INTO orders VALUES (1,1,1,'2026-01-01')"])
def test_data_server_blocks(sql):
    with pytest.raises(ValueError):
        data.run_query(sql=sql)


def test_data_server_caps_rows():
    r = data.run_query(sql="SELECT * FROM orders")
    assert len(r["rows"]) == 500 and "LIMIT 500" in r["sql"]


def test_docs_acl(monkeypatch):
    assert [d["id"] for d in docs.search_docs(query="exit code 137 memory")] == []
    monkeypatch.setenv("MCP_ROLE", "data-platform")
    assert docs.search_docs(query="exit code 137 memory")[0]["id"] == "oom-runbook"


def test_docs_no_existence_oracle():
    with pytest.raises(ValueError, match="not found"):
        docs.get_doc(doc_id="payroll-calendar")


def test_audit_log_redacts_and_records_denials():
    try:
        itsm.create_ticket(title="Reset password=hunter2 please", description="x", priority="P3")
    except PermissionDenied:
        pass
    recs = [json.loads(l) for l in open(os.environ["MCP_AUDIT_LOG"])]
    last = recs[-1]
    assert last["status"] == "error" and "PermissionDenied" in last["error"]
    assert "hunter2" not in json.dumps(last)
