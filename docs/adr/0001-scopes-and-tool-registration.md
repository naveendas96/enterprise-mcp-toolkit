# ADR 0001: Read/write separation by tool registration *and* call-time checks
**Decision:** Each server process gets scopes from `MCP_SCOPES` (the default is read-only). Write tools are **not registered** unless their write scope is granted, so the model never sees them. Every tool function is also wrapped by `@audit(server, scope)`, which re-checks the scope on every call.
**Why:** It's defence in depth. Hiding tools cuts prompt-injection blast radius, and the call-time check stops misconfiguration or direct invocation.
**Consequences:** Running read and write as separate server entries (see examples/) makes human approval policies in MCP clients simple.
