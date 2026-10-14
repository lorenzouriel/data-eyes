# Data Eyes — SQL Server Monitoring, Performance & Maintenance Toolkit

Open-source toolkit for complete visibility and best-practice automation on Microsoft SQL Server. The monitoring pipeline lives in `monitor/`: a Python collector, Prometheus, and Grafana. The MCP server and the "Ask" agent stay at the repository root, with separate collector inventory (`instances.yaml`) and MCP access policy (`mcp-access.yaml`). The collector runs trusted fixed read-only queries against the fleet and exposes cached `/metrics`; Prometheus keeps 30 days of history and recording rules; Grafana is the UI (Fleet Overview dashboard) and does the alerting (rules, contact point, policy). MCP exposes only collector-backed monitoring tools; the agent uses MCP, and only the collector connects to SQL Server.

## Repository Structure
```text
data-eyes/
|-- monitor/                 Monitoring pipeline (collector -> Prometheus -> Grafana), README.md
|   |-- collector/
|   |   |-- app/main.py      FastAPI app: /metrics and /health, startup
|   |   |-- app/config.py    Settings, instances.yaml, checks.yaml
|   |   |-- app/sql.py       SQL Server client (lanes, timeouts, app name)
|   |   |-- app/scheduler.py Collection loops and cached Prometheus samples
|   |   |-- app/metrics.py   7 metric groups (30 s; databases every 5 min) and their SQL
|   |   |-- app/alerts/      catalog (56 checks in 7 groups), evaluation, checks/ (6 modules)
|   |   |-- app/verify.py    Pre-production check: SQL Server truth vs Prometheus values
|   |   `-- checks.yaml      Alert check overrides (thresholds, per-instance settings)
|   |-- prometheus/          Scrape config (30 s), 3 recording rules (no alerting rules)
|   `-- grafana/             The UI: grafana.ini (home = Fleet Overview), provisioning/ (Prometheus datasource,
|                            dashboards, alerting: 6 rules + email contact point + policy, plugins: none), dashboards/ (1)
|-- agent/
|   `-- app/                 "Ask" assistant API (internal, no UI): main (/api/agent/status, /api/agent/ask SSE),
|                            agent (tool loop), tools (4 read-only Prometheus tools), mcp_tools (MCP client:
|                            13 allow-listed health diagnostics as sql_<tool>, routed per instance to dev/staging/prod
|                            MCP as the ui-agent principal), config (anthropic | openai | local)
|-- mcp/
|   |-- src/data_eyes_mcp/   main, config, auth, tools (collector-backed monitoring)
|   |-- tests/               Config, auth, db, and tool tests
|   `-- sql/                 SQL Server login provisioning (read-only, alerting permissions)
|-- assets/                  Project branding (logo.png, logo.svg)
|-- docs/                    Empty (architecture docs not yet written)
|-- .github/workflows/       security.yml (collector/agent imports, MCP tests, promtool, image builds, pip-audit, gitleaks)
|-- .claude/                 2 agents, 12 commands, static KB (5 files), SQL toolkits
|   `-- resources/
|       |-- performance/     4 diagnostic queries + 5 JSON variants, 5 docs, tuning workbook
|       |-- maintenance/     2 playbooks, 7 diagnostics, 3 Ola Hallengren use cases
|       `-- sql-scripts/     84 scripts across 18 sub-folders: audit 2, backup_recovery 8,
|                            custom_alert_emails 2, database_size 7, free_space 3, functions 1,
|                            helps 10, index 10, lock 3, query_store 10, server 4, sql_access 7,
|                            sql_agent 5, sql_docker 0, sql_profiler 2, ssis 3, ssrs 6, triggers 1
|-- README.md                Full setup, configuration, services, MCP, security guide
|-- CONTRIBUTING.md, LICENSE
|-- instances.yaml           Local shared fleet file; ignored by Git (template: instances.example.yaml)
|-- docker-compose.yml       Integrated stack (collector, Prometheus, Grafana, agent, MCP dev/staging/prod profiles, loadtest loadgen)
`-- .mcp.json                Local MCP client registration (stdio, dev instance)
```

## Key Conventions

- All SQL scripts are *copy-paste safe* — never auto-execute destructive operations
- Scripts that CREATE/ALTER/DROP objects require explicit user confirmation
- Connection via $MSSQL_CONNECTION env var or manual credential prompt
- Ola Hallengren parameters use @Databases, @Directory, @CleanupTime etc.
- Prefer a live `data-eyes-mcp` tool call over reading a script as text whenever an MCP server is reachable — scripts remain the reference/copy-paste source, not the primary path (see `sql-server-dba` agent's Knowledge Resolution order)
- The root `docker-compose.yml` starts the collector, Prometheus, Grafana, agent, UI and MCP. Only the collector mounts `instances.yaml` and connects to SQL. MCP mounts credential-free `mcp-access.yaml`; `.env` configures Grafana and the agent. Run one collector per checkpoint volume. Never display secrets.

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

- **Static domain KB** (`.claude/knowledge-base/_static/`) — thresholds, taxonomy, naming conventions, methodology, and the scripts index. All diagnostic SQL lives in the collector (`monitor/collector/app/metrics.py`, `monitor/collector/app/alerts/checks/`). Alert catalog defaults (`monitor/collector/app/alerts/catalog.py`) mirror the `alerts:` section of `thresholds.yaml` — change both together; deployment overrides go in `monitor/collector/checks.yaml`. Alert checks live only in the collector, and MCP sees their results as `alert.<key>` history from Prometheus.
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
