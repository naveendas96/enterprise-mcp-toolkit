# ADR 0002: Structured audit log for every tool call
**Decision:** One JSONL record per call with ts, server, tool, scope, actor, redacted args, status or error, a result SHA-256 prefix and latency. Denials are logged too.
**Why:** Security teams need to answer "what did the agent do, as whom, and what came back?" Hashing the result avoids storing sensitive payloads while still allowing tamper or replay checks.
**Consequences:** Ship to a SIEM via a file shipper. Rotation is left to the platform.
