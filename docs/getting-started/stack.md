> **Security upgrade:** Read the [setup and migration guide](../security/security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Data Eyes application

The repository root contains the complete deployable system. The dashboard backend
and MCP server consume one shared `instances.yaml` fleet configuration and use
one PostgreSQL repository for application state and collected history.

## Components

| Directory | Responsibility | Guide |
|---|---|---|
| `frontend/` | React and TypeScript dashboard | [Dashboard](../features/dashboard.md) |
| `backend/` | FastAPI API, SQL diagnostics, auth, and collection | [Dashboard](../features/dashboard.md) |
| `mcp/` | Fleet-aware MCP tools for agents | [MCP server](../features/mcp.md) |
| `repository/` | PostgreSQL initialization schema | [Repository](../architecture/repository.md) |
| `instances.yaml` | Local shared SQL Server fleet | [Configuration](configuration.md) |
| `docker-compose.yml` | Integrated runtime | [Deployment](deployment.md) |

For component relationships and data flow, see the
[architecture guide](../architecture/architecture.md).

## Run

From the repository root:

```powershell
Copy-Item .env.example .env
   Copy-Item instances.example.yaml instances.yaml
Copy-Item backend/.env.example backend/.env
Copy-Item mcp/.env.example mcp/.env
docker compose -f docker-compose.yml up -d --build
```

The Compose project name remains `src` to preserve existing named volumes.

| Service | Address |
|---|---|
| Dashboard | <https://localhost:8443> |
| Backend health | <https://localhost:8443/api/health> |
| MCP | <http://localhost:8080/mcp> |
| MCP readiness | <http://localhost:8080/ready> |

Read the [documentation index](../README.md) for setup, development, and
operational details.
