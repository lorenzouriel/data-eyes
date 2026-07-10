# Data Eyes — SQL Server Monitoring, Performance & Maintenance Toolkit

Open-source toolkit for complete visibility and best-practice automation on Microsoft SQL Server.

## Repository Structure
```
data-eyes/
├── monitor/              Grafana + Prometheus monitoring stack (Docker)
│   ├── docker-compose.yml
│   ├── grafana/          dashboards, datasources, alerts, config
│   └── docs/             panel documentation (8 topic files)
├── performance/          10-step performance tuning methodology
│   ├── performance_tuning_workbook.xlsx
│   └── additional_queries/   4 diagnostic SQL scripts + docs
├── maintenance/          Ola Hallengren maintenance automation
│   ├── playbook.sql
│   ├── sql_agent_schedule_playbook.sql
│   └── use_cases/        35+ scenarios (backup, integrity, index)
├── sql-scripts/          80+ reusable DBA scripts across 18 topics
│   ├── audit/            backup_recovery/   custom_alert_emails/
│   ├── database_size/    free_space/         functions/
│   ├── helps/            index/              lock/
│   ├── query_store/      server/             sql_access/
│   ├── sql_agent/        sql_docker/         sql_profiler/
│   ├── ssis/             ssrs/               triggers/
│   └── README.md
└── .claude/
    ├── settings.json
    ├── commands/data-eyes/   slash commands
    ├── agents/               specialist agents
    └── knowledge-base/       database volume KBs
```

## Key Conventions

- All SQL scripts are *copy-paste safe* — never auto-execute destructive operations
- Scripts that CREATE/ALTER/DROP objects require explicit user confirmation
- Connection via $MSSQL_CONNECTION env var or manual credential prompt
- Ola Hallengren parameters use @Databases, @Directory, @CleanupTime etc.
- Monitor stack uses Docker Compose with .env for secrets (never display .env contents)

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
| /sql-monitor | Diagnose and configure Grafana monitoring stack |
| /sql-performance | Systematic performance tuning (10-step methodology) |
| /sql-guidelines | Review SQL against clean code guidelines |
| /sql-scripts | Find and adapt scripts from the 80+ script library |
| /sql-kb | Build knowledge base for a database (volumes, indexes) |
| /sql-pr-review | Review SQL changes against KB + guidelines + performance rules |
| /sql-visual-report | Generate HTML report for performance/maintenance changes (SQL Server red + Grafana orange) |
| /status | Project health report — components, monitor stack, KB freshness |
| /sync-context | Update CLAUDE.md with current repo structure |
| /memory | Save valuable DBA session insights to storage |

## Knowledge Base

Database-specific knowledge bases live in .claude/knowledge-base/<database-name>.md.
Built by /sql-kb, consumed by /sql-pr-review. Contains:
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