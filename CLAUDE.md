# Data Eyes — SQL Server Monitoring, Performance & Maintenance Toolkit

Open-source toolkit for complete visibility and best-practice automation on Microsoft SQL Server. The deployable services live at the repository root: a Python collector, Prometheus, Grafana, the MCP server, a Caddy gateway, and the shared `instances.yaml` fleet configuration. The collector runs trusted fixed read-only queries against the fleet and exposes cached `/metrics`; Prometheus keeps 30 days of history; Grafana provides dashboards, alerting, and user accounts. MCP exposes the same configured fleet to agents and reads history from Prometheus.

## Repository Structure
```text
data-eyes/
|-- collector/
|   |-- app/main.py          FastAPI app: /metrics and /health, startup
|   |-- app/config.py        Settings, instances.yaml, checks.yaml
|   |-- app/sql.py           SQL Server client (lanes, timeouts, app name)
|   |-- app/scheduler.py     Collection loops and cached Prometheus samples
|   |-- app/metrics.py       7 metric groups (30 s; databases every 5 min) and their SQL
|   |-- app/alerts/          catalog (56 checks in 7 groups), evaluation, checks/ (6 modules)
|   |-- tests/               Alert checks, evaluation, configuration, exporter, HTTP, SQL client
|   `-- checks.yaml          Alert check overrides (thresholds, per-instance settings)
|-- prometheus/              Scrape config (30 s), 3 recording rules
|-- grafana/
|   |-- dashboards/          4 dashboards: fleet, instance, database, health
|   `-- provisioning/        Datasource, dashboard provider, 6 alert rules, contact-point template
|-- gateway/                 Caddy HTTPS :8443 (Grafana at /, MCP at /mcp, /staging/mcp, /production/mcp)
|-- mcp/
|   |-- src/data_eyes_mcp/   main, config, auth, db, output, queries (diagnostic SQL), tools (27 tools)
|   |-- tests/               Config, auth, db, and tool tests
|   `-- sql/                 SQL Server login provisioning (read-only, alerting permissions)
|-- assets/                  Project branding
|-- .github/workflows/       security.yml (MCP tests, promtool, image builds, pip-audit, gitleaks)
|-- .claude/                 2 agents, 12 commands, static KB (5 files), SQL toolkits
|   `-- resources/
|       |-- performance/     9 diagnostic queries (+ JSON variants), 5 docs, tuning workbook
|       |-- maintenance/     2 playbooks, 7 diagnostics, 3 Ola Hallengren use cases
|       `-- sql-scripts/     84 scripts across 18 sub-folders
|-- README.md                Full setup, configuration, services, MCP, security guide
|-- instances.yaml           Local shared fleet file; ignored by Git (template: instances.example.yaml)
|-- docker-compose.yml       Integrated stack (MCP dev/staging/prod profiles, gateway, collector, Prometheus, Grafana)
`-- .mcp.json                Local MCP client registration (stdio, dev instance)
```

## Key Conventions

- All SQL scripts are *copy-paste safe* — never auto-execute destructive operations
- Scripts that CREATE/ALTER/DROP objects require explicit user confirmation
- Connection via $MSSQL_CONNECTION env var or manual credential prompt
- Ola Hallengren parameters use @Databases, @Directory, @CleanupTime etc.
- Prefer a live `data-eyes-mcp` tool call over reading a script as text whenever an MCP server is reachable — scripts remain the reference/copy-paste source, not the primary path (see `sql-server-dba` agent's Knowledge Resolution order)
- `docker-compose.yml` starts the collector, Prometheus, Grafana, MCP, and gateway together; both SQL-facing services (collector, MCP) read `instances.yaml`. Run exactly one collector per checkpoint volume. Never display `.env` contents or connection strings.

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
| /sql-monitor | Diagnose and configure the Data Eyes monitoring stack (collector, Prometheus, Grafana) |
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

- **Static domain KB** (`.claude/knowledge-base/_static/`) — thresholds, taxonomy, naming conventions, methodology, and the scripts index. Diagnostic severity SQL for the MCP tools lives in `mcp/src/data_eyes_mcp/queries.py`; keep it synchronized with the KB. The collector keeps its own fixed SQL (`collector/app/metrics.py`, `collector/app/alerts/checks/`). Alert catalog defaults (`collector/app/alerts/catalog.py`) mirror the `alerts:` section of `thresholds.yaml` — change both together; deployment overrides go in `collector/checks.yaml`. Alert checks live only in the collector, and MCP sees their results as `alert.<key>` history from Prometheus.
- **Per-database KB** (none built yet) (`.claude/knowledge-base/<database-name>.md`) — built by /sql-kb, consumed by /sql-pr-review. Contains:
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
