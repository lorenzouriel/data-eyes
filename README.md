<div align="center">
  <img src="assets/logo.png" alt="Data Eyes logo" width="180">
</div>

# Data Eyes

[![GitHub stars](https://img.shields.io/github/stars/lorenzouriel/data-eyes?style=social)](https://github.com/lorenzouriel/data-eyes/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/lorenzouriel/data-eyes)](https://github.com/lorenzouriel/data-eyes/issues)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Data Eyes is an open-source SQL Server observability and operations toolkit. It
combines a fleet dashboard, a Model Context Protocol (MCP) server for agent
access, a PostgreSQL history repository, and reusable performance and
maintenance resources.

The deployable services live in the root `backend/`, `frontend/`, `gateway/`,
`mcp/`, and `repository/` folders. The dashboard and MCP server
use the same [`instances.yaml`](docs/getting-started/configuration.md#shared-instance-file)
fleet definition, so a SQL Server instance is configured once and exposed
consistently to both interfaces.

## Start here

1. Copy the example configuration files:

   ```powershell
   Copy-Item .env.example .env
   Copy-Item instances.example.yaml instances.yaml
   Copy-Item backend/.env.example backend/.env
   Copy-Item mcp/.env.example mcp/.env
   ```

2. Configure the fleet and required secrets. See
   [Configuration](docs/getting-started/configuration.md).

3. Start the complete stack from the repository root:

   ```powershell
   docker compose -f docker-compose.yml up -d --build
   ```

4. Open the dashboard at <https://localhost:8443>.

See the [deployment guide](docs/getting-started/deployment.md) for validation, updates,
troubleshooting, and non-Docker development.

## Project map

| Area | Purpose | Documentation | Source |
|---|---|---|---|
| Dashboard frontend | React fleet UI and instance drill-down | [Dashboard](docs/features/dashboard.md) | [`frontend/`](frontend) |
| Dashboard backend | FastAPI API, SQL diagnostics, authentication, and collection | [Dashboard](docs/features/dashboard.md) | [`backend/`](backend) |
| MCP server | Safe, fleet-aware SQL Server tools for agents | [MCP server](docs/features/mcp.md) | [`mcp/`](mcp) |
| Repository | PostgreSQL registry, users, trends, and events | [Repository](docs/architecture/repository.md) | [`repository/`](repository) |
| Shared configuration | One fleet definition for dashboard and MCP | [Configuration](docs/getting-started/configuration.md) | [`instances.example.yaml`](instances.example.yaml) |
| SQL toolkits | Performance, maintenance, and reusable SQL scripts | [SQL toolkits](docs/integrations/sql-toolkits.md) | [`.claude/resources/`](.claude/resources) |
| Agent integration | Commands, specialist agents, and knowledge routing | [Agent integration](docs/integrations/agent-integration.md) | [`.claude/`](.claude) |

## Documentation

The [documentation index](docs/README.md) is the canonical guide to the
project. Start with:

- [Architecture](docs/architecture/architecture.md) — components, boundaries, and data flow
- [Configuration](docs/getting-started/configuration.md) — instances, secrets, and environment variables
- [Deployment](docs/getting-started/deployment.md) — Docker Compose and operational checks
- [Development](docs/development/development.md) — local workflows, tests, and contribution paths

## Runtime endpoints

| Service | Default address |
|---|---|
| Dashboard | <https://localhost:8443> |
| Backend health | <https://localhost:8443/api/health> |
| MCP endpoint | <http://localhost:8080/mcp> |
| MCP liveness | <http://localhost:8080/health> |
| MCP readiness | <http://localhost:8080/ready> |

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Data Eyes is
released under the [MIT License](LICENSE).
