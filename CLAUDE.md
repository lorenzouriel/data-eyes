# Data Eyes — SQL Server Monitoring, Performance & Maintenance Toolkit

Open-source toolkit for complete visibility and best-practice automation on Microsoft SQL Server. The deployable services live at the repository root: the dashboard, MCP gateway, PostgreSQL repository, and shared `instances.yaml` fleet configuration. The dashboard runs trusted fixed queries directly; MCP exposes the same configured fleet to agents and reads the shared trend repository. The old Grafana stack has been removed.

## Repository Structure
```text
data-eyes/
|-- docs/                    Architecture, setup, features, security, integrations
|-- backend/
|   |-- app/core/            Settings, encryption, shared limits
|   |-- app/infrastructure/  PostgreSQL pool/schema, SQL Server client
|   |-- app/modules/         Auth, users, instances, monitoring, insights, alerts, notifications
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

## Key Conventions

- All SQL scripts are *copy-paste safe* — never auto-execute destructive operations
- Scripts that CREATE/ALTER/DROP objects require explicit user confirmation
- Connection via $MSSQL_CONNECTION env var or manual credential prompt
- Ola Hallengren parameters use @Databases, @Directory, @CleanupTime etc.
- Prefer a live `data-eyes-mcp` tool call over reading a script as text whenever an MCP server is reachable — scripts remain the reference/copy-paste source, not the primary path (see `sql-server-dba` agent's Knowledge Resolution order)
- `docker-compose.yml` starts the dashboard, MCP, and PostgreSQL together; both SQL-facing services read `instances.yaml`. Never display `.env` contents or connection strings.

## SQL Naming Standards (Data Eyes Guidelines)

- Tables: singular snake_case (customer, order_item)
- Columns: snake_case (first_name, email_address)
- PKs: [entity]_id (never bare id)
- FKs: fk_[table]_[referenced_table]
- Procedures: usp_[verb]_[entity] (never sp_ prefix)
- Views: vw_[entity]_[purpose]
- Indexes: ix_[table]_[col] (unique), nix_[table]_[col] (non-unique)
- Keywords: UPPERCASE, one clause per line, 4-space indent

## Slash Commands

| Command | Purpose |
|---------|---------|
| /sql-document | Generate database documentation from catalog views |
| /sql-maintenance | Set up maintenance using Ola Hallengren scripts |
| /sql-monitor | Diagnose and configure the Data Eyes dashboard app |
| /sql-performance | Systematic performance tuning (10-step methodology) |
| /sql-guidelines | Review SQL against clean code guidelines |
| /sql-scripts | Find and adapt scripts from the 84-script library |
| /sql-kb | Build knowledge base for a database (volumes, indexes) |
| /sql-pr-review | Review SQL changes against KB + guidelines + performance rules |
| /sql-visual-report | Generate HTML report for performance/maintenance changes (Data Eyes violet + aqua) |
| /status | Project health report — components, monitor stack, KB freshness |
| /sync-context | Update CLAUDE.md with current repo structure |
| /memory | Save valuable DBA session insights to storage |

## Knowledge Base

Two layers:

- **Static domain KB** (`.claude/knowledge-base/_static/`) — thresholds, taxonomy, naming conventions, methodology, and the scripts index. Severity SQL is duplicated between `mcp/src/data_eyes_mcp/tools/diagnostics` and `backend/app/modules/monitoring/diagnostics`; keep both synchronized with the KB. Alert catalog defaults (`backend/app/modules/alerts/catalog.py`) mirror the `alerts:` section of `thresholds.yaml`, enforced by `test_alert_catalog.py`; alert checks live only in the backend, and MCP sees their results as `alert.<key>` snapshots.
- **Per-database KB** (`.claude/knowledge-base/<database-name>.md`) — built by /sql-kb, consumed by /sql-pr-review. Contains:
  - Table volumes with SMALL/MEDIUM/HIGH/CRITICAL classification
  - Existing index inventory with usage stats
  - Missing index hints from DMV
  - Unused index candidates
  - SQL Server version/edition capabilities

## Safety Rules

- NEVER display or store passwords — reference $MSSQL_CONNECTION by name only
- NEVER display .env file contents — only reference variable names
- NEVER run DDL/DML without explicit user confirmation
- NEVER recommend DROP INDEX without telling user to measure impact first
- ONLINE = ON requires Enterprise Edition — always check KB header
- Scripts 01-11, 14-16 are read-only (DMV queries); scripts 12-13 create objects — confirm first
- One change at a time, measure before AND after (Step 9: Verify)
