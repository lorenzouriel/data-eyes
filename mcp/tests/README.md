# MCP tests

Run `uv run --project mcp --extra dev pytest mcp/tests -q` from the repository root.
Tests use synthetic policies and mocked Prometheus responses; no SQL or provider credentials.
Cover authentication, authorization, environment scoping, escaping, bounds, freshness, and HTTP MCP transport.
