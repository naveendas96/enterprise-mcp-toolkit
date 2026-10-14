.PHONY: install test demo inspect
install: ; pip install -e ".[dev]"
test: ; pytest -q
demo: ; python examples/demo_client.py
inspect: ; npx @modelcontextprotocol/inspector mcp-itsm
