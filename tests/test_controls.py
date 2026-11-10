import asyncio
import json
import os

import pytest

from emcp import data, itsm, refund
from emcp.governance import (
    KillSwitchEngaged,
    PermissionDenied,
    ServerCardDenied,
    card_allows,
    engage_kill_switch,
    load_server_card,
)


def _audit():
    return [json.loads(l) for l in open(os.environ["MCP_AUDIT_LOG"])]


def test_default_server_card_lists_builtin_tools():
    card = load_server_card()
    assert card_allows("itsm", "get_ticket")
    assert card_allows("refund", "request_refund")
    assert not card_allows("finance-db", "run_query")
    assert not card_allows("itsm", "delete_ticket")
    assert set(card["servers"]) == {"itsm", "data", "docs", "refund"}


def test_kill_switch_blocks_every_tool_and_is_logged():
    engage_kill_switch()
    with pytest.raises(KillSwitchEngaged, match="all tool calls blocked"):
        itsm.get_ticket(ticket_id="INC0001")
    rec = _audit()[-1]
    assert rec["denied_by"] == "kill_switch" and rec["status"] == "error"
    assert rec["tool"] == "get_ticket" and "KillSwitchEngaged" in rec["error"]


def test_kill_switch_env_flag_blocks_write_tool(monkeypatch):
    monkeypatch.setenv("MCP_KILL_SWITCH", "true")
    monkeypatch.setenv("MCP_SCOPES", "refund:write")
    with pytest.raises(KillSwitchEngaged):
        refund.request_refund(order_id="ORD-1001", amount=49.99, reason="duplicate charge")
    assert _audit()[-1]["denied_by"] == "kill_switch"


def test_kill_switch_checked_before_scope_or_card():
    engage_kill_switch()
    with pytest.raises(KillSwitchEngaged):
        itsm.create_ticket(title="Printer on fire", description="x", priority="P3")
    rec = _audit()[-1]
    assert rec["denied_by"] == "kill_switch"
    assert "PermissionDenied" not in rec["error"]


def test_server_card_denies_tool_not_on_card(tmp_path, monkeypatch):
    card = tmp_path / "card.json"
    card.write_text(json.dumps({"name": "restricted", "servers": {"itsm": ["get_ticket"]}}))
    monkeypatch.setenv("MCP_SERVER_CARD", str(card))
    assert itsm.get_ticket(ticket_id="INC0001")["id"] == "INC0001"
    with pytest.raises(ServerCardDenied, match="itsm.search_tickets"):
        itsm.search_tickets(query="vpn")
    rec = _audit()[-1]
    assert rec["denied_by"] == "server_card" and rec["tool"] == "search_tickets"


def test_unknown_server_is_denied_by_card():
    assert card_allows("data", "run_query")
    assert not card_allows("shadow", "exfiltrate")


def test_request_refund_hidden_without_scope():
    assert "request_refund" not in {t.name for t in asyncio.run(refund.build().list_tools())}


def test_request_refund_blocked_without_scope():
    with pytest.raises(PermissionDenied):
        refund.request_refund(order_id="ORD-1001", amount=49.99, reason="duplicate charge")


def test_request_refund_runs_three_steps_in_order(monkeypatch):
    monkeypatch.setenv("MCP_SCOPES", "refund:write")
    out = refund.request_refund(order_id="ORD-1001", amount=49.99, reason="duplicate charge")
    assert out["steps"] == ["eligibility", "approval", "credit"]
    assert out["approval"]["status"] == "approved" and out["approval"]["approval_id"].startswith("APR-")
    assert out["credit"]["credit_id"] == "CR-ORD-1001" and out["credit"]["refunded_total"] == 49.99
    assert refund.ORDERS["ORD-1001"]["refunded"] == 49.99


def test_request_refund_ineligible_shipped_order(monkeypatch):
    monkeypatch.setenv("MCP_SCOPES", "refund:write")
    with pytest.raises(ValueError, match="shipped"):
        refund.request_refund(order_id="ORD-1002", amount=10.0, reason="too early")


def test_pipeline_cannot_skip_approval():
    pipe = refund.RefundPipeline("ORD-1004", 80.0, "broken item")
    pipe.run_eligibility()
    with pytest.raises(ValueError, match="cannot run 'credit'; next required step is 'approval'"):
        pipe.run_credit()
    assert refund.ORDERS["ORD-1004"]["refunded"] == 0.0


def test_pipeline_cannot_reorder_credit_first():
    with pytest.raises(ValueError, match="cannot run 'credit'; next required step is 'eligibility'"):
        refund.run_refund_steps("ORD-1004", 80.0, "broken item", ["credit", "eligibility", "approval"])
    assert refund.ORDERS["ORD-1004"]["refunded"] == 0.0


def test_pipeline_rejects_unknown_step():
    with pytest.raises(ValueError, match="unknown step"):
        refund.run_refund_steps("ORD-1001", 1.0, "x", ["eligibility", "skip", "credit"])
