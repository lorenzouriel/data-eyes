# Data Eyes Commands

**12 slash commands** for SQL Server monitoring, performance, maintenance, code review, visual reporting, and project management.

## DBA Operations (6)

| Command | Description |
|---------|-------------|
| `/sql-document` | Generate database documentation from catalog views |
| `/sql-maintenance` | Set up maintenance using Ola Hallengren scripts |
| `/sql-monitor` | Diagnose and configure the Data Eyes dashboard app |
| `/sql-performance` | Systematic performance tuning (10-step methodology) |
| `/sql-guidelines` | Review SQL against clean code guidelines |
| `/sql-scripts` | Find and adapt scripts from the 80+ script library |

## Knowledge-Driven Review (2)

| Command | Description | Dependency |
|---------|-------------|------------|
| `/sql-kb` | Build knowledge base for a database (volumes, indexes) | Run first |
| `/sql-pr-review` | Review SQL changes against KB + guidelines + performance rules | Requires `/sql-kb` |

## Visual Reporting (1)

| Command | Description |
|---------|-------------|
| `/sql-visual-report` | Self-contained HTML report for performance tuning and maintenance changes. Data Eyes violet (`#4a3aa7`) + aqua (`#1baf7a`) branding. Supports `--branch-diff`, `--kb`, session context. |

## Project Management (3)

| Command | Description |
|---------|-------------|
| `/status` | Health report — components, monitor stack, KB freshness, recommendations |
| `/sync-context` | Update CLAUDE.md with current repo structure and script inventory |
| `/memory` | Save valuable DBA session insights (findings, decisions, gotchas) |

## Usage

```bash
# Project health check
/status

# Keep CLAUDE.md current
/sync-context

# Save session insights
/memory "Diagnosed CPU spike on na-shard1"

# Build knowledge base (run once per database)
/sql-kb exampleDB

# Review SQL changes with volume awareness
/sql-pr-review "ALTER TABLE session ADD COLUMN recording_type TINYINT NOT NULL DEFAULT 0"
/sql-pr-review --branch-diff main

# Performance investigation
/performance "high CPU, queries slowed down"

# Find a script
/sql-scripts "check blocking sessions"

# Set up maintenance
/maintenance "weekly index optimization for all user databases"

# Dashboard app troubleshooting
/sql-monitor "the dashboard says prod1 is unreachable"
```

## Agents

| Agent | Description |
|-------|-------------|
| `sql-server-dba` | SQL Server troubleshooting, performance tuning, maintenance |
| `dashboard-app` | Data Eyes dashboard app configuration and diagnostics |

Agents are in `.claude/agents/` and are automatically available via the Agent tool.
