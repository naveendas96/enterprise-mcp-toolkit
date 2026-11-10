# Changelog

## Unreleased

- Added a "Run it in 60 seconds" section to the README (install + `make test && make demo`). The documented command now uses `python3` rather than `python3.11`.
- Added GitHub issue and pull request templates.
- Added tests that `list_tables` only returns allowlisted tables, that a caller `LIMIT` below the 500-row cap is kept, and that `get_ticket` returns a known ticket and errors on an unknown id.

## 0.1.0 - 2026-10-14

Initial public release: three governed MCP servers (ITSM, data query, document search) with scope-based tool registration, audit logging and input validation.
