"""Document search server: BM25 over a local KB with per-document role ACLs."""
from __future__ import annotations

import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from rank_bm25 import BM25Okapi

from .governance import audit, run

KB = Path(os.getenv("MCP_KB_DIR", Path(__file__).resolve().parents[2] / "data" / "kb"))
TOK = re.compile(r"[a-z0-9]+")


def _load() -> list[dict]:
    docs = []
    for p in sorted(KB.glob("*.md")):
        lines = p.read_text().splitlines()
        roles = lines[0].removeprefix("roles:").strip().split(",") if lines[0].startswith("roles:") else ["admin"]
        docs.append({"id": p.stem, "roles": [r.strip() for r in roles], "text": "\n".join(lines[1:]).strip()})
    return docs


DOCS = _load()
INDEX = BM25Okapi([TOK.findall(d["text"].lower()) for d in DOCS])


def _role() -> str:
    return os.getenv("MCP_ROLE", "employee")


def _ok(d: dict) -> bool:
    return _role() == "admin" or _role() in d["roles"]


@audit("docs", "docs:read")
def search_docs(query: str, k: int = 3) -> list[dict]:
    if not 2 <= len(query) <= 500:
        raise ValueError("query must be 2-500 chars")
    scores = INDEX.get_scores(TOK.findall(query.lower()))
    order = sorted(range(len(DOCS)), key=lambda i: -scores[i])
    out = [{"id": DOCS[i]["id"], "score": round(float(scores[i]), 3), "snippet": DOCS[i]["text"][:240]}
           for i in order if scores[i] > 0 and _ok(DOCS[i])]
    return out[:max(1, min(k, 10))]


@audit("docs", "docs:read")
def get_doc(doc_id: str) -> dict:
    d = next((d for d in DOCS if d["id"] == doc_id), None)
    if d is None or not _ok(d):  # same error for missing and forbidden: no existence oracle
        raise ValueError(f"document not found: {doc_id}")
    return {"id": d["id"], "text": d["text"]}


def build() -> MCPServer:
    srv = MCPServer("docs", instructions="Search internal documents. Results are filtered by the caller's role.")
    for f in (search_docs, get_doc):
        srv.tool(annotations=ToolAnnotations(readOnlyHint=True))(f)
    return srv


def main() -> None:
    run(build())

if __name__ == "__main__":
    main()
