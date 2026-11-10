import os
import tempfile

import pytest

from emcp.governance import release_kill_switch
from emcp.refund import reset_orders

os.environ["MCP_AUDIT_LOG"] = os.path.join(tempfile.mkdtemp(), "audit.jsonl")
os.environ["MCP_SCOPES"] = "itsm:read,data:read,docs:read"
os.environ.pop("MCP_KILL_SWITCH", None)
os.environ.pop("MCP_SERVER_CARD", None)


@pytest.fixture(autouse=True)
def _reset_controls():
    release_kill_switch()
    reset_orders()
    yield
    release_kill_switch()
    reset_orders()
