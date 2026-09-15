# Data Eyes application

This directory contains the complete deployable system. The dashboard backend
and MCP server consume one shared `instances.yaml` fleet configuration and use
one PostgreSQL repository for application state and collected history.

## Components

| Directory | Responsibility | Guide |
|---|---|---|
| `frontend/` | React and TypeScript dashboard | [Dashboard](../docs/dashboard.md) |
| `backend/` | FastAPI API, SQL diagnostics, auth, and collection | [Dashboard](../docs/dashboard.md) |
| `mcp/` | Fleet-aware MCP tools for agents | [MCP server](../docs/mcp.md) |
| `repository/` | PostgreSQL initialization schema | [Repository](../docs/repository.md) |
| `instances.yaml` | Local shared SQL Server fleet | [Configuration](../docs/configuration.md) |
| `docker-compose.yml` | Integrated runtime | [Deployment](../docs/deployment.md) |

For component relationships and data flow, see the
[architecture guide](../docs/architecture.md).

## Run

From the repository root:

```powershell
Copy-Item src/instances.example.yaml src/instances.yaml
Copy-Item src/backend/.env.example src/backend/.env
Copy-Item src/mcp/.env.example src/mcp/.env
docker compose -f src/docker-compose.yml up -d --build
```

From this directory:

```powershell
docker compose up -d --build
```

| Service | Address |
|---|---|
| Dashboard | <http://localhost:8091> |
| Backend health | <http://localhost:8090/api/health> |
| MCP | <http://localhost:8080/mcp> |
| MCP readiness | <http://localhost:8080/ready> |

Read the [documentation index](../docs/README.md) for setup, development, and
operational details.
