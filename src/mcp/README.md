> **Security upgrade:** Read the [setup and migration guide](../../docs/security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Data Eyes MCP server

This package is the agent-facing interface to Data Eyes. It provides
fleet-aware, policy-guarded SQL Server exploration and DBA tools over stdio or
Streamable HTTP.

The canonical guide is [docs/mcp.md](../../docs/mcp.md). Related guides:

- [Architecture](../../docs/architecture.md)
- [Shared configuration](../../docs/configuration.md)
- [Deployment](../../docs/deployment.md)
- [Development](../../docs/development.md)
- [MCP security model](../../docs/mcp-security.md)

## Quick local start

```powershell
cd src/mcp
python -m pip install -e ".[dev]"
python -m data_eyes_mcp.cli --transport http --bind 127.0.0.1:8080
```

In the integrated stack, start MCP together with the dashboard and repository:

```powershell
docker compose -f src/docker-compose.yml up -d --build
```

The shared fleet belongs in `src/instances.yaml`; do not duplicate production
connection strings in MCP client configuration.
