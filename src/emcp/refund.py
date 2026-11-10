"""Refund server. request_refund always runs eligibility, approval, then credit. Steps cannot be skipped or reordered."""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .governance import audit, has, run

STEPS = ("eligibility", "approval", "credit")
ELIGIBLE_STATUS = {"delivered", "cancelled"}


def _seed() -> dict[str, dict[str, Any]]:
    # Synthetic catalog only. Amounts are in USD.
    return {
        "ORD-1001": {"paid": 49.99, "status": "delivered", "refunded": 0.0},
        "ORD-1002": {"paid": 120.00, "status": "shipped", "refunded": 0.0},
        "ORD-1003": {"paid": 15.00, "status": "delivered", "refunded": 15.00},
        "ORD-1004": {"paid": 80.00, "status": "delivered", "refunded": 0.0},
    }


ORDERS: dict[str, dict[str, Any]] = _seed()


def reset_orders() -> None:
    ORDERS.clear()
    ORDERS.update(_seed())


class RefundPipeline:
    """Fixed three-step refund. Each step must follow the one before it."""

    def __init__(self, order_id: str, amount: float, reason: str) -> None:
        self.order_id = order_id
        self.amount = float(amount)
        self.reason = reason
        self.completed: list[str] = []
        self.approval_id: str | None = None
        self.credit_id: str | None = None
        self.eligibility: dict[str, Any] | None = None

    def _require(self, step: str) -> None:
        nxt = STEPS[len(self.completed)] if len(self.completed) < len(STEPS) else None
        if step != nxt:
            expected = nxt or "no further steps"
            raise ValueError(f"cannot run '{step}'; next required step is '{expected}'")

    def run_eligibility(self) -> dict[str, Any]:
        self._require("eligibility")
        order = ORDERS.get(self.order_id)
        if order is None:
            raise ValueError(f"unknown order {self.order_id}")
        remaining = round(float(order["paid"]) - float(order["refunded"]), 2)
        if order["status"] not in ELIGIBLE_STATUS:
            raise ValueError(f"order {self.order_id} is {order['status']}, not eligible for refund")
        if self.amount <= 0 or self.amount > remaining:
            raise ValueError(f"amount {self.amount} is not refundable; remaining {remaining}")
        self.eligibility = {"order_id": self.order_id, "amount": self.amount, "remaining": remaining, "ok": True}
        self.completed.append("eligibility")
        return dict(self.eligibility)

    def run_approval(self) -> dict[str, Any]:
        self._require("approval")
        # Placeholder approval: records an id. A real deployment would wait on a human or a policy engine.
        self.approval_id = f"APR-{self.order_id}"
        self.completed.append("approval")
        return {"approval_id": self.approval_id, "status": "approved", "order_id": self.order_id, "amount": self.amount}

    def run_credit(self) -> dict[str, Any]:
        self._require("credit")
        if not self.approval_id:
            raise ValueError("credit requires an approval id from the approval step")
        order = ORDERS[self.order_id]
        order["refunded"] = round(float(order["refunded"]) + self.amount, 2)
        self.credit_id = f"CR-{self.order_id}"
        self.completed.append("credit")
        return {"credit_id": self.credit_id, "approval_id": self.approval_id,
                "order_id": self.order_id, "amount": self.amount, "refunded_total": order["refunded"]}

    def run_step(self, step: str) -> dict[str, Any]:
        fns = {"eligibility": self.run_eligibility, "approval": self.run_approval, "credit": self.run_credit}
        if step not in fns:
            raise ValueError(f"unknown step {step}")
        return fns[step]()

    def run_all(self) -> dict[str, Any]:
        return {"steps": list(STEPS), "eligibility": self.run_eligibility(),
                "approval": self.run_approval(), "credit": self.run_credit()}


def run_refund_steps(order_id: str, amount: float, reason: str, steps: list[str]) -> dict[str, Any]:
    """Run named steps on a new pipeline. Out-of-order or skipped steps raise ValueError."""
    pipe = RefundPipeline(order_id, amount, reason)
    results = [pipe.run_step(s) for s in steps]
    return {"steps": list(pipe.completed), "results": results}


@audit("refund", "refund:write")
def request_refund(order_id: str, amount: float, reason: str) -> dict:
    """Always runs eligibility, approval, then credit. This tool has no way to skip or reorder those steps."""
    if not str(reason).strip():
        raise ValueError("reason is required")
    return RefundPipeline(order_id, float(amount), str(reason).strip()).run_all()


def build() -> MCPServer:
    srv = MCPServer("refund", instructions="Refunds always run eligibility, a placeholder approval, then credit, in that order.")
    if has("refund:write"):
        srv.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))(request_refund)
    return srv


def main() -> None:
    run(build())


if __name__ == "__main__":
    main()
