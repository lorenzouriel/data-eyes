# Data Eyes documentation

This directory contains the canonical documentation for Data Eyes. The root
README is intentionally a short project map; details belong here or in the
README of the resource being documented.

## Core system

| Guide | What it explains |
|---|---|
| [Architecture](architecture/architecture.md) | Runtime components, boundaries, and end-to-end data flow |
| [Configuration](getting-started/configuration.md) | Shared fleet YAML, environment variables, precedence, and secrets |
| [Dashboard](features/dashboard.md) | Frontend, backend API, collection, health evaluation, and insights |
| [Alerts](features/alerts.md) | Alert catalog, per-alert and per-instance controls, permissions, daily checklist |
| [Notifications](features/notifications.md) | Delivery channels, alert rules, and retries |
| [MCP server](features/mcp.md) | Transports, tool groups, safety policy, fleet routing, and health endpoints |
| [Repository](architecture/repository.md) | PostgreSQL responsibilities, stored data, encryption, and retention |
| [Security hardening](security/security-hardening.md) | Changes, rationale, token/TLS setup, upgrade steps, and limits |
| [Deployment](getting-started/deployment.md) | Docker Compose startup, verification, updates, and troubleshooting |
| [Development](development/development.md) | Local setup, source layout, tests, and common workflows |

## Supporting systems

| Guide | What it explains |
|---|---|
| [SQL toolkits](integrations/sql-toolkits.md) | Performance methodology, maintenance automation, and script library |
| [Agent integration](integrations/agent-integration.md) | Repository commands, specialist agents, knowledge base, and MCP routing |

## Product

| Guide | What it explains |
|---|---|
| [Product plan](plan/product-plan.md) | Open-source and paid subscription lines, pricing, roadmap, and risks |

## Documentation ownership

- Cross-component behavior is documented in this directory.
- Component-local commands may also be summarized in [the stack guide](getting-started/stack.md)
  and [`mcp/README.md`](../mcp/README.md).
- Individual SQL resources retain their own README files under
  [`.claude/resources/`](../.claude/resources).
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) defines contribution expectations.

When behavior and documentation disagree, treat the source and
[`docker-compose.yml`](../docker-compose.yml) as authoritative and
update the relevant guide in the same change.
