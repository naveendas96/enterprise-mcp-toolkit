"""ITSM ticket server (mock ServiceNow-style). Write tools are only registered when itsm:write is granted."""
from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .governance import audit, has, run

Priority = Literal["P1", "P2", "P3", "P4"]
State = Literal["new", "in_progress", "resolved", "closed"]


class Ticket(BaseModel):
    id: str
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(max_length=4000)
    priority: Priority
    state: State = "new"
    assignment_group: str = "service-desk"


TICKETS: dict[str, Ticket] = {t.id: t for t in [
    Ticket(id="INC0001", title="VPN disconnects every 10 minutes", description="Users in Pune office", priority="P2", assignment_group="network"),
    Ticket(id="INC0002", title="Payroll report job failed", description="Nightly batch error code 137", priority="P1", state="in_progress", assignment_group="data-platform"),
    Ticket(id="INC0003", title="Request new laptop for joiner", description="Starts Monday", priority="P4", assignment_group="end-user"),
]}
TRANSITIONS = {"new": {"in_progress", "closed"}, "in_progress": {"resolved"}, "resolved": {"closed", "in_progress"}, "closed": set()}

S = "itsm"


@audit(S, "itsm:read")
def get_ticket(ticket_id: str) -> dict:
    if ticket_id not in TICKETS:
        raise ValueError(f"unknown ticket {ticket_id}")
    return TICKETS[ticket_id].model_dump()


@audit(S, "itsm:read")
def search_tickets(query: str = "", state: State | None = None, priority: Priority | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 50))
    q = query.lower()
    rows = [t for t in TICKETS.values() if (not q or q in (t.title + " " + t.description).lower())
            and (state is None or t.state == state) and (priority is None or t.priority == priority)]
    return [t.model_dump() for t in rows[:limit]]


@audit(S, "itsm:write")
def create_ticket(title: str, description: str, priority: Priority, assignment_group: str = "service-desk") -> dict:
    t = Ticket(id=f"INC{len(TICKETS) + 1:04d}", title=title, description=description, priority=priority,
               assignment_group=assignment_group)
    TICKETS[t.id] = t
    return t.model_dump()


@audit(S, "itsm:write")
def update_ticket_state(ticket_id: str, new_state: State) -> dict:
    t = TICKETS[ticket_id]
    if new_state not in TRANSITIONS[t.state]:
        raise ValueError(f"illegal transition {t.state} -> {new_state}")
    t.state = new_state
    return t.model_dump()


def build() -> MCPServer:
    srv = MCPServer("itsm", instructions="Mock ITSM. Read tools are safe; write tools require itsm:write.")
    ro = ToolAnnotations(readOnlyHint=True)
    srv.tool(annotations=ro)(get_ticket)
    srv.tool(annotations=ro)(search_tickets)
    if has("itsm:write"):
        rw = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
        srv.tool(annotations=rw)(create_ticket)
        srv.tool(annotations=rw)(update_ticket_state)
    return srv


def main() -> None:
    run(build())

if __name__ == "__main__":
    main()
