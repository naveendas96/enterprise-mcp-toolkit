"""Cross-cutting controls shared by all servers: scopes, audit log, redaction."""
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


class PermissionDenied(PermissionError):
    pass


def scopes() -> set[str]:
    """Scopes granted to this server process (e.g. 'itsm:read,itsm:write'). Default: read-only."""
    return {s.strip() for s in os.getenv("MCP_SCOPES", "itsm:read,data:read,docs:read").split(",") if s.strip()}


def has(scope: str) -> bool:
    return scope in scopes()


def redact(v: Any) -> Any:
    return SECRET.sub(r"\1=[REDACTED]", v) if isinstance(v, str) else v


def audit(server: str, scope: str) -> Callable[[F], F]:
    """Enforce scope and write one JSONL audit record per call (args redacted, result hashed)."""
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            rec: dict[str, Any] = {"ts": time.time(), "server": server, "tool": fn.__name__, "scope": scope,
                                   "actor": os.getenv("MCP_ACTOR", "unknown"),
                                   "args": {k: redact(v) for k, v in kwargs.items()}}
            t0 = time.perf_counter()
            try:
                if not has(scope):
                    raise PermissionDenied(f"scope '{scope}' not granted")
                out = fn(*args, **kwargs)
                rec.update(status="ok", result_sha=hashlib.sha256(json.dumps(out, default=str).encode()).hexdigest()[:16])
                return out
            except Exception as e:
                rec.update(status="error", error=f"{type(e).__name__}: {e}")
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
