# Data Eyes application

The deployable Data Eyes system lives in this directory. One shared
`instances.yaml` file configures both the dashboard and the MCP gateway.

## Services

- `frontend/`: React and Vite dashboard UI
- `backend/`: FastAPI API, direct SQL Server diagnostics, authentication, and collection
- `mcp/`: fleet-aware MCP tools for agents
- `repository/`: PostgreSQL schema for users, the encrypted dashboard registry, and history
- `docker-compose.yml`: launches the complete system

The dashboard executes its trusted monitoring queries directly against SQL
Server. MCP exposes the same YAML-defined servers to agents and reads historical
snapshots from the same PostgreSQL repository.

## Configuration

Create the local fleet file:

```bash
cp src/instances.example.yaml src/instances.yaml
```

Each entry requires a unique `name`, a display `label`, and an
`mssql_connection_string`; `environment` is optional. Never commit the real
file—it is ignored by Git because it normally contains credentials.

At startup, the dashboard upserts YAML entries into its encrypted registry.
Matching YAML entries override the stored copy; entries created only through
the dashboard UI are preserved but remain dashboard-only. MCP reads the YAML
directly and exposes `list_configured_instances`; all live tools accept an
`instance` argument.

Restart the stack after changing the YAML so the dashboard synchronizes it.

## Run

From the repository root:

```bash
cp src/backend/.env.example src/backend/.env
cp src/mcp/.env.example src/mcp/.env
docker compose -f src/docker-compose.yml up -d --build
```

If your terminal is already inside `src/`, use
`docker compose up -d --build` (do not prefix the file path with `src/` again).

- Dashboard: `http://localhost:8091`
- Backend API: `http://localhost:8090`
- MCP: `http://localhost:8080/mcp`
- MCP liveness/readiness: `/health` and `/ready`

The root `.mcp.json` also launches `src/mcp` over stdio for local MCP clients.
