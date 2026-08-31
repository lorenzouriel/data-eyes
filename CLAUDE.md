# Data Eyes — SQL Server Monitoring, Performance & Maintenance Toolkit

Open-source toolkit for complete visibility and best-practice automation on Microsoft SQL Server. The way to *see* a fleet is the custom `dashboard/` app (a DPA-style Main Page + per-database drill-down + embedded insights agent), which connects directly to each monitored SQL Server and manages its own database-backed instance registry and user accounts. `mcp/`'s `data-eyes-mcp` server is separate and agent-only — it's what Claude Code (and the dashboard's embedded insights agent, for trend-history lookups) talks to, not what the dashboard uses to render itself. The old Grafana-based `monitor/` stack has been removed; its panel categories all have live equivalents in `dashboard/` (see `.claude/knowledge-base/_static/taxonomy.md`).

## Repository Structure
```
data-eyes/
├── dashboard/            Custom Data Eyes dashboard app (replaces monitor/'s Grafana stack)
│   ├── backend/          FastAPI — connects directly to SQL Server (diagnostics.py, mssql_client.py),
│   │                     fleet health rollup, real user accounts, DB-backed instance registry,
│   │                     trend collector, insights agent
│   ├── frontend/         React + TS + Vite — Main Page, per-database tabbed drill-down,
│   │                     instance/user management
│   └── repository/       Schema for the dashboard's own Postgres DB — trend history,
│                         instance registry, user accounts
├── mcp/                  data-eyes-mcp server — agent-only (Claude Code's sql-server-dba agent);
│                         NOT used by the dashboard, which queries SQL Server directly
│   ├── src/data_eyes_mcp/   generic tools (tools.py) + DBA diagnostic tools (dba_tools.py, 11 tools)
│   │                        + dashboard-repository trend tools (repository_tools.py, 3 tools)
│   └── docker-compose.yml   single instance
└── .claude/
    ├── settings.json
    ├── commands/data-eyes/   12 slash commands
    ├── agents/               sql-server-dba, dashboard-app
    ├── knowledge-base/
    │   ├── _static/          shared static KB: thresholds.yaml, taxonomy.md, naming-conventions.md, methodology.md, scripts-index.md
    │   └── <database>.md     per-database volume/index KBs (built by /sql-kb)
    └── resources/            secondary, agent-supporting toolkits — not required to run the dashboard
        ├── performance/      10-step performance tuning methodology
        │   ├── performance_tuning_workbook.xlsx
        │   └── additional_queries/   9 diagnostic SQL scripts (severity-classified *.json.sql + originals) + docs
        ├── maintenance/      Ola Hallengren maintenance automation
        │   ├── playbook.sql
        │   ├── sql_agent_schedule_playbook.sql
        │   ├── use_cases/    35+ scenarios (backup, integrity, index)
        │   └── diagnostics/  7 live read-only diagnostic scripts (backup, CHECKDB, fragmentation, blocking, AG, jobs, space) + docs
        └── sql-scripts/      84 reusable DBA scripts across 18 topics
            ├── audit/            backup_recovery/   custom_alert_emails/
            ├── database_size/    free_space/         functions/
            ├── helps/            index/              lock/
            ├── query_store/      server/             sql_access/
            ├── sql_agent/        sql_docker/         sql_profiler/
            ├── ssis/             ssrs/               triggers/
            └── README.md
```

## Key Conventions

- All SQL scripts are *copy-paste safe* — never auto-execute destructive operations
- Scripts that CREATE/ALTER/DROP objects require explicit user confirmation
- Connection via $MSSQL_CONNECTION env var or manual credential prompt
- Ola Hallengren parameters use @Databases, @Directory, @CleanupTime etc.
- Prefer a live `data-eyes-mcp` tool call over reading a script as text whenever an MCP server is reachable — scripts remain the reference/copy-paste source, not the primary path (see `sql-server-dba` agent's Knowledge Resolution order)
- `dashboard/` and `mcp/` use Docker Compose with `.env` for secrets (never display .env contents); the dashboard additionally encrypts stored SQL Server connection strings at rest (`app/crypto.py`) — never display or log a decrypted one outside `app/diagnostics.py`'s actual connection use

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

- **Static domain KB** (`.claude/knowledge-base/_static/`) — thresholds, taxonomy, naming conventions, methodology, and the scripts index. Single source of truth for severity bands and the category ↔ tab ↔ script routing table; the actual `CASE WHEN` severity thresholds are duplicated (deliberately, a documented drift risk) between `mcp/`'s `dba_tools.py` and `dashboard/backend/app/diagnostics.py`, both driven by this KB. Consumed by the `sql-server-dba`/`dashboard-app` agents alike.
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