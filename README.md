<div align="center">
  <img src="assets/logo-gradient-nobg.png" alt="Data Eyes logo" width="180">
</div>

# Data Eyes

[![GitHub stars](https://img.shields.io/github/stars/lorenzouriel/data-eyes?style=social)](https://github.com/lorenzouriel/data-eyes/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/lorenzouriel/data-eyes)](https://github.com/lorenzouriel/data-eyes/issues)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Data Eyes is an open-source SQL Server observability and operations toolkit. It
combines a fleet dashboard, a Model Context Protocol (MCP) server for agent
access, a PostgreSQL history repository, and reusable performance and
maintenance resources.

The deployable application lives in [`src/`](src/). The dashboard and MCP server
use the same [`src/instances.yaml`](docs/configuration.md#shared-instance-file)
fleet definition, so a SQL Server instance is configured once and exposed
consistently to both interfaces.

## Start here

1. Copy the example configuration files:

   ```powershell
   Copy-Item src/instances.example.yaml src/instances.yaml
   Copy-Item src/backend/.env.example src/backend/.env
   Copy-Item src/mcp/.env.example src/mcp/.env
   ```

2. Configure the fleet and required secrets. See
   [Configuration](docs/configuration.md).

3. Start the complete stack from the repository root:

   ```powershell
   docker compose -f src/docker-compose.yml up -d --build
   ```

4. Open the dashboard at <http://localhost:8091>.

See the [deployment guide](docs/deployment.md) for validation, updates,
troubleshooting, and non-Docker development.

## Project map

| Area | Purpose | Documentation | Source |
|---|---|---|---|
| Dashboard frontend | React fleet UI and instance drill-down | [Dashboard](docs/dashboard.md) | [`src/frontend/`](src/frontend/) |
| Dashboard backend | FastAPI API, SQL diagnostics, authentication, and collection | [Dashboard](docs/dashboard.md) | [`src/backend/`](src/backend/) |
| MCP server | Safe, fleet-aware SQL Server tools for agents | [MCP server](docs/mcp.md) | [`src/mcp/`](src/mcp/) |
| Repository | PostgreSQL registry, users, trends, and events | [Repository](docs/repository.md) | [`src/repository/`](src/repository/) |
| Shared configuration | One fleet definition for dashboard and MCP | [Configuration](docs/configuration.md) | [`src/instances.example.yaml`](src/instances.example.yaml) |
| SQL toolkits | Performance, maintenance, and reusable SQL scripts | [SQL toolkits](docs/sql-toolkits.md) | [`.claude/resources/`](.claude/resources/) |
| Agent integration | Commands, specialist agents, and knowledge routing | [Agent integration](docs/agent-integration.md) | [`.claude/`](.claude/) |

## Documentation

The [documentation index](docs/README.md) is the canonical guide to the
project. Start with:

- [Architecture](docs/architecture.md) — components, boundaries, and data flow
- [Configuration](docs/configuration.md) — instances, secrets, and environment variables
- [Deployment](docs/deployment.md) — Docker Compose and operational checks
- [Development](docs/development.md) — local workflows, tests, and contribution paths

## Runtime endpoints

| Service | Default address |
|---|---|
| Dashboard | <http://localhost:8091> |
| Backend health | <http://localhost:8090/api/health> |
| MCP endpoint | <http://localhost:8080/mcp> |
| MCP liveness | <http://localhost:8080/health> |
| MCP readiness | <http://localhost:8080/ready> |

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Data Eyes is
released under the [MIT License](LICENSE).
