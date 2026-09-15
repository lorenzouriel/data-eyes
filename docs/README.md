# Data Eyes documentation

This directory contains the canonical documentation for Data Eyes. The root
README is intentionally a short project map; details belong here or in the
README of the resource being documented.

## Core system

| Guide | What it explains |
|---|---|
| [Architecture](architecture.md) | Runtime components, boundaries, and end-to-end data flow |
| [Configuration](configuration.md) | Shared fleet YAML, environment variables, precedence, and secrets |
| [Dashboard](dashboard.md) | Frontend, backend API, collection, health evaluation, and insights |
| [MCP server](mcp.md) | Transports, tool groups, safety policy, fleet routing, and health endpoints |
| [Repository](repository.md) | PostgreSQL responsibilities, stored data, encryption, and retention |
| [Deployment](deployment.md) | Docker Compose startup, verification, updates, and troubleshooting |
| [Development](development.md) | Local setup, source layout, tests, and common workflows |

## Supporting systems

| Guide | What it explains |
|---|---|
| [SQL toolkits](sql-toolkits.md) | Performance methodology, maintenance automation, and script library |
| [Agent integration](agent-integration.md) | Repository commands, specialist agents, knowledge base, and MCP routing |

## Documentation ownership

- Cross-component behavior is documented in this directory.
- Component-local commands may also be summarized in [`src/README.md`](../src/README.md)
  and [`src/mcp/README.md`](../src/mcp/README.md).
- Individual SQL resources retain their own README files under
  [`.claude/resources/`](../.claude/resources/).
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) defines contribution expectations.

When behavior and documentation disagree, treat the source and
[`src/docker-compose.yml`](../src/docker-compose.yml) as authoritative and
update the relevant guide in the same change.
