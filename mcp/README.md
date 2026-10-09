> **Security:** Read the [security hardening guide](../docs/security/security-hardening.md) before deploying. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Data Eyes MCP server

This package is the agent-facing interface to Data Eyes. It provides
fixed, read-only SQL Server exploration and DBA tools for the configured fleet
over stdio or Streamable HTTP.

```text
src/data_eyes_mcp/
  main.py     arguments, logging with secret redaction, stdio/HTTP startup
  config.py   settings and instances.yaml (instances + principals), cached by mtime
  auth.py     bearer-token middleware, tool/instance grants, rate limit, audit log
  db.py       scoped-login connections, timeouts with cursor cancel, row/byte caps
  output.py   JSON envelope that marks rows as untrusted database content
  queries.py  fixed diagnostic SQL and severity rules
  tools.py    all 27 tools: discovery, diagnostics, Prometheus history
```

The canonical guide is [docs/features/mcp.md](../docs/features/mcp.md). Related guides:

- [Architecture](../docs/architecture/architecture.md)
- [Shared configuration](../docs/getting-started/configuration.md)
- [Deployment](../docs/getting-started/deployment.md)
- [Development](../docs/development/development.md)
- [MCP security model](../docs/security/mcp-security.md)

## Quick local start

```powershell
cd mcp
uv sync --extra dev
uv run pytest
uv run data-eyes-mcp --transport http --bind 127.0.0.1:8080
```

In the integrated stack, start MCP together with the Grafana, Prometheus, and collector:

```powershell
docker compose -f docker-compose.yml up -d --build
```

The shared fleet belongs in `instances.yaml`; do not duplicate production
connection strings in MCP client configuration.
