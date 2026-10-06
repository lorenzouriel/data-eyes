> **Security upgrade:** Read the [setup and migration guide](../security/security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Development

This guide covers source layout and local workflows. For the integrated runtime
model, read [Architecture](../architecture/architecture.md) first.

## Source layout

```text
data-eyes/
|-- docs/                    Architecture, setup, features, security, integrations
|-- backend/
|   |-- app/core/            Settings, encryption, shared limits
|   |-- app/infrastructure/  PostgreSQL pool/schema, SQL Server client
|   |-- app/modules/         Auth, users, instances, monitoring, insights, notifications
|   `-- tests/modules/       Tests grouped by feature
|-- frontend/
|   |-- src/app/             Routing, providers, application shell
|   |-- src/features/        Feature pages, components, hooks, API calls, types
|   `-- src/shared/          HTTP client, common types, components, styles
|-- gateway/                Caddy TLS and reverse-proxy configuration
|-- mcp/
|   |-- src/data_eyes_mcp/   Core, security, database, tools, transport, observability
|   |-- tests/              Core and security regression tests
|   `-- sql/                SQL Server login provisioning
|-- repository/init/        PostgreSQL first-run initialization
|-- assets/                 Project branding
|-- .github/                CI workflows
|-- .claude/                Agent definitions, commands, knowledge, SQL toolkits
|-- instances.yaml          Local shared fleet file; ignored by Git
|-- docker-compose.yml      Integrated stack
`-- .mcp.json               Local MCP client registration
```

After moving an existing checkout, recreate virtual environments with `uv sync
--frozen --extra dev` from each Python service directory; installed scripts may
contain paths from their previous location.

Generated folders such as Python virtual environments, frontend
`node_modules`, build output, and coverage caches are not source modules.

## Module boundaries

Backend features own their routers, behavior, and PostgreSQL queries. Shared
connection pools and clients belong in `app/infrastructure/`; settings and
encryption belong in `app/core/`. `main.py` assembles routes and middleware;
`lifespan.py` owns startup and background workers.

Frontend features own their pages, components, hooks, `api.ts`, and `types.ts`
where needed. `shared/api/client.ts` owns HTTP and streaming behavior. Create
shared components only when multiple features use them.

MCP tool modules register against `tools/registry.py`. The `tools` package
registers discovery, query, history, and diagnostic families. Transport context,
authorization, and database execution remain separate. The Python package name
stays `data_eyes_mcp`, preserving the CLI and installed entry point.

The backend and MCP remain independently installable. Neither imports the other.
Keep their fixed diagnostic SQL and severity thresholds synchronized.

## Backend development

Requirements: Python 3.10+, PostgreSQL, Microsoft ODBC Driver 17 or 18, and
network access to a configured SQL Server.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8090
```

The backend requires the values documented in
[Configuration](../getting-started/configuration.md#backend-environment). You can run PostgreSQL
through Compose while developing the API locally.

## Frontend development

Requirements: a current Node.js LTS release and npm.

```powershell
cd frontend
npm install
npm run dev
```

The Vite server defaults to port 5173. Ensure the backend allows
`http://localhost:5173` through `CORS_ALLOW_ORIGINS`.

Build the production bundle with:

```powershell
npm run build
```

## MCP development

```powershell
cd mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m data_eyes_mcp.cli --transport http --bind 127.0.0.1:8080
```

For an MCP client, use stdio mode by omitting `--transport http`. The root
`.mcp.json` is already pointed at this component.

## Tests and checks

Run MCP tests:

```powershell
cd mcp
python -m pytest
```

Run backend tests:

```powershell
cd backend
python -m pytest -o asyncio_mode=auto
```

Check the frontend production build:

```powershell
cd frontend
npm run build
```

Validate Compose interpolation and structure:

```powershell
docker compose -f docker-compose.yml config --quiet
```

## Change routing

| Change | Primary area | Documentation to review |
|---|---|---|
| Dashboard UI or navigation | `frontend/src/` | `docs/features/dashboard.md` |
| Dashboard API or diagnostics | `backend/app/` | `docs/features/dashboard.md`, `docs/architecture/repository.md` |
| Fleet schema or precedence | backend config and MCP config | `docs/getting-started/configuration.md`, `docs/architecture/architecture.md` |
| MCP tool behavior | `mcp/src/data_eyes_mcp/` | `docs/features/mcp.md` |
| Repository schema | `repository/init/10-init.sql` | `docs/architecture/repository.md`, migration notes |
| Compose services or ports | `docker-compose.yml` | `docs/getting-started/deployment.md` |
| SQL operational resources | `.claude/resources/` | `docs/integrations/sql-toolkits.md` and local resource README |

Keep secrets out of fixtures, logs, screenshots, and commits. Use
`instances.example.yaml` for safe structural examples.
