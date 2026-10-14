import os
import tempfile

os.environ["MCP_AUDIT_LOG"] = os.path.join(tempfile.mkdtemp(), "audit.jsonl")
os.environ["MCP_SCOPES"] = "itsm:read,data:read,docs:read"
