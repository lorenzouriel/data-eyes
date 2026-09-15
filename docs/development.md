# Development

This guide covers source layout and local workflows. For the integrated runtime
model, read [Architecture](architecture.md) first.

## Source layout

```text
data-eyes/
|-- docs/                    Cross-component documentation
|-- src/
|   |-- backend/             FastAPI dashboard backend
|   |-- frontend/            React and TypeScript dashboard frontend
|   |-- mcp/                 Python MCP server
|   |-- repository/          PostgreSQL initialization schema
|   |-- instances.yaml       Local shared fleet file; ignored by Git
|   `-- docker-compose.yml   Integrated stack
|-- .claude/
|   |-- agents/              Specialist agent definitions
|   |-- commands/            Repository workflows
|   |-- knowledge-base/      Routing and domain knowledge
|   `-- resources/           SQL performance and maintenance toolkits
|-- .mcp.json                Local MCP client registration
`-- CONTRIBUTING.md
```

Generated folders such as Python virtual environments, frontend
`node_modules`, build output, and coverage caches are not source modules.

## Backend development

Requirements: Python 3.10+, PostgreSQL, Microsoft ODBC Driver 17 or 18, and
network access to a configured SQL Server.

```powershell
cd src/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
```

The backend requires the values documented in
[Configuration](configuration.md#backend-environment). You can run PostgreSQL
through Compose while developing the API locally.

## Frontend development

Requirements: a current Node.js LTS release and npm.

```powershell
cd src/frontend
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
cd src/mcp
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
cd src/mcp
python -m pytest
```

Run backend tests when present:

```powershell
cd src/backend
python -m pytest
```

Check the frontend production build:

```powershell
cd src/frontend
npm run build
```

Validate Compose interpolation and structure:

```powershell
docker compose -f src/docker-compose.yml config --quiet
```

## Change routing

| Change | Primary area | Documentation to review |
|---|---|---|
| Dashboard UI or navigation | `src/frontend/src/` | `docs/dashboard.md` |
| Dashboard API or diagnostics | `src/backend/app/` | `docs/dashboard.md`, `docs/repository.md` |
| Fleet schema or precedence | backend config and MCP config | `docs/configuration.md`, `docs/architecture.md` |
| MCP tool behavior | `src/mcp/src/data_eyes_mcp/` | `docs/mcp.md` |
| Repository schema | `src/repository/init.sql` | `docs/repository.md`, migration notes |
| Compose services or ports | `src/docker-compose.yml` | `docs/deployment.md` |
| SQL operational resources | `.claude/resources/` | `docs/sql-toolkits.md` and local resource README |

Keep secrets out of fixtures, logs, screenshots, and commits. Use
`src/instances.example.yaml` for safe structural examples.
