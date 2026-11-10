"""Cross-cutting controls shared by all servers: scopes, audit log, redaction, kill switch, server card."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])
SECRET = re.compile(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+")
_DEFAULT_CARD_PATH = Path(__file__).resolve().parents[2] / "data" / "server-card.json"
_BUILTIN_CARD = {
    "name": "enterprise-mcp-toolkit",
    "version": "1",
    "servers": {
        "itsm": ["get_ticket", "search_tickets", "create_ticket", "update_ticket_state"],
        "data": ["list_tables", "run_query"],
        "docs": ["search_docs", "get_doc"],
        "refund": ["request_refund"],
    },
}

_kill_switch = False


class PermissionDenied(PermissionError):
    pass


class KillSwitchEngaged(PermissionError):
    pass


class ServerCardDenied(PermissionError):
    pass


def scopes() -> set[str]:
    """Scopes granted to this server process (e.g. 'itsm:read,itsm:write'). Default: read-only."""
    return {s.strip() for s in os.getenv("MCP_SCOPES", "itsm:read,data:read,docs:read").split(",") if s.strip()}


def has(scope: str) -> bool:
    return scope in scopes()


def redact(v: Any) -> Any:
    return SECRET.sub(r"\1=[REDACTED]", v) if isinstance(v, str) else v


def engage_kill_switch() -> None:
    global _kill_switch
    _kill_switch = True


def release_kill_switch() -> None:
    global _kill_switch
    _kill_switch = False


def kill_switch_on() -> bool:
    env = os.getenv("MCP_KILL_SWITCH", "").strip().lower()
    return _kill_switch or env in {"1", "true", "on", "yes"}


def load_server_card(path: str | None = None) -> dict[str, Any]:
    """Load the allowlist of servers and tools. MCP_SERVER_CARD overrides the built-in card."""
    raw = path if path is not None else os.getenv("MCP_SERVER_CARD")
    p = Path(raw) if raw else (_DEFAULT_CARD_PATH if _DEFAULT_CARD_PATH.is_file() else None)
    if p is None:
        return {"name": _BUILTIN_CARD["name"], "version": _BUILTIN_CARD["version"],
                "servers": {k: list(v) for k, v in _BUILTIN_CARD["servers"].items()}}
    data = json.loads(p.read_text())
    if not isinstance(data.get("servers"), dict):
        raise ValueError("server card must have a 'servers' map of server name -> tool list")
    return data


def card_allows(server: str, tool: str) -> bool:
    allowed = load_server_card().get("servers", {}).get(server)
    return bool(allowed) and tool in allowed


def audit(server: str, scope: str) -> Callable[[F], F]:
    """Enforce kill switch, server card and scope, and write one JSONL audit record per call."""
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            rec: dict[str, Any] = {"ts": time.time(), "server": server, "tool": fn.__name__, "scope": scope,
                                   "actor": os.getenv("MCP_ACTOR", "unknown"),
                                   "args": {k: redact(v) for k, v in kwargs.items()}}
            t0 = time.perf_counter()
            try:
                if kill_switch_on():
                    raise KillSwitchEngaged("kill switch engaged: all tool calls blocked")
                if not card_allows(server, fn.__name__):
                    raise ServerCardDenied(f"tool '{server}.{fn.__name__}' is not listed on the server card")
                if not has(scope):
                    raise PermissionDenied(f"scope '{scope}' not granted")
                out = fn(*args, **kwargs)
                rec.update(status="ok", result_sha=hashlib.sha256(json.dumps(out, default=str).encode()).hexdigest()[:16])
                return out
            except Exception as e:
                rec.update(status="error", error=f"{type(e).__name__}: {e}")
                if isinstance(e, KillSwitchEngaged):
                    rec["denied_by"] = "kill_switch"
                elif isinstance(e, ServerCardDenied):
                    rec["denied_by"] = "server_card"
                raise
            finally:
                rec["ms"] = round((time.perf_counter() - t0) * 1000, 2)
                p = Path(os.getenv("MCP_AUDIT_LOG", "logs/audit.jsonl"))
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
        return wrapper  # type: ignore[return-value]
    return deco


def run(server: Any) -> None:
    import sys
    server.run("streamable-http", host="0.0.0.0") if "--http" in sys.argv else server.run()
