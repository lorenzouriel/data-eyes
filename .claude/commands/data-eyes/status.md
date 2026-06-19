---
name: status
description: Data Eyes project health report — monitor stack, maintenance coverage, script inventory, KB freshness, and recommendations
---

# /status Command

> Generate a comprehensive health report for the Data Eyes toolkit

## Usage

```bash
/status                    # Full project status report
/status "sprint review"    # Status with specific context
```

---

## What It Does

1. **Scans** all four toolkit components (monitor, performance, maintenance, sql-scripts)
2. **Checks** monitor stack health (Docker containers, datasource config)
3. **Audits** knowledge base freshness and coverage
4. **Counts** script inventory across all 18 sub-folders
5. **Generates** actionable recommendations

---

## Execution Process

Execute all steps inline (no agent delegation).

### Step 1: Scan Toolkit Components

```text
# Monitor stack
Glob("monitor/docker-compose.yml")
Glob("monitor/grafana/dashboards/*.json")
Glob("monitor/grafana/datasources.yml")
Glob("monitor/grafana/alerts-and-notifiers.yml")
Glob("monitor/docs/*.md")

# Performance toolkit
Glob("performance/additional_queries/*.sql")
Glob("performance/additional_queries/docs/*.md")
Glob("performance/performance_tuning_workbook.xlsx")

# Maintenance
Glob("maintenance/*.sql")
Glob("maintenance/use_cases/*.sql")

# SQL Scripts library
Glob("sql-scripts/**/*.sql")
```

Count files in each component.

### Step 2: Check Monitor Stack Health

```bash
# Check if Docker is available
docker --version 2>/dev/null || echo "Docker not installed"

# Check if monitor stack is running (only if Docker available)
docker-compose -f monitor/docker-compose.yml ps 2>/dev/null || echo "Stack not running"

# Check if .env exists for monitor
ls monitor/.env 2>/dev/null || echo "No .env file — stack will fail to start"
```

Read `monitor/grafana/datasources.yml` — extract SQL Server connection target (server name only, never credentials).

### Step 3: Audit Knowledge Base

```text
Glob(".claude/knowledge-base/*.md")
```

For each KB file found:
- Read first 10 lines to extract: Generated date, Server, EngineEdition, MajorVersion
- Calculate age in days from generated date
- Flag if older than 30 days

### Step 4: Script Inventory

Count `.sql` files per sub-folder in `sql-scripts/`:

```text
Glob("sql-scripts/audit/*.sql")
Glob("sql-scripts/backup_recovery/**/*.sql")
Glob("sql-scripts/custom_alert_emails/*.sql")
Glob("sql-scripts/database_size/*.sql")
Glob("sql-scripts/free_space/*.sql")
Glob("sql-scripts/functions/*.sql")
Glob("sql-scripts/helps/**/*.sql")
Glob("sql-scripts/index/*.sql")
Glob("sql-scripts/lock/*.sql")
Glob("sql-scripts/query_store/*.sql")
Glob("sql-scripts/server/*.sql")
Glob("sql-scripts/sql_access/*.sql")
Glob("sql-scripts/sql_agent/*.sql")
Glob("sql-scripts/sql_profiler/*.sql")
Glob("sql-scripts/ssis/*.sql")
Glob("sql-scripts/ssrs/*.sql")
Glob("sql-scripts/triggers/*.sql")
```

### Step 5: Check Git State

```bash
git log --oneline -5
git status --short
git branch --show-current
```

### Step 6: Check .claude Health

```text
# Commands
Glob(".claude/commands/data-eyes/*.md")

# Agents
Glob(".claude/agents/*.md")

# CLAUDE.md
Glob("CLAUDE.md")
```

### Step 7: Generate Report

---

## Output Format

```markdown
# Data Eyes — Status Report

**Branch:** {current branch}
**Date:** {today's date}

---

## Toolkit Components

| Component | Files | Status | Notes |
|-----------|-------|--------|-------|
| Monitor (Grafana) | {N} dashboards, {N} docs | {Running/Stopped/Unknown} | Target: {server from datasource} |
| Performance | {N} scripts, {N} docs, workbook | Present | 10-step methodology |
| Maintenance | {N} playbooks, {N} use cases | Present | Ola Hallengren |
| SQL Scripts | {N} scripts across {N} folders | Present | 18 topic areas |

## Monitor Stack

| Check | Status |
|-------|--------|
| Docker installed | {Yes/No} |
| Stack running | {Yes/No/Unknown} |
| .env file | {Present/Missing} |
| Datasource configured | {Yes — target: server} |
| Dashboards provisioned | {N} dashboards |
| Alerts configured | {Yes/No} |

## Knowledge Base

| Database | Generated | Age | Server | Edition | Version | Status |
|----------|-----------|-----|--------|---------|---------|--------|
| {name} | {date} | {N} days | {server} | {edition} | {version} | {Fresh/Stale} |

> {If no KB files: "No knowledge bases found. Run `/sql-kb <database>` to build one."}

## Script Inventory

| Sub-folder | Scripts | Coverage |
|------------|---------|----------|
| audit/ | {N} | {topics covered} |
| backup_recovery/ | {N} | |
| ... | ... | |
| **Total** | **{N}** | **18 topics** |

## .claude Configuration

| Item | Count | Status |
|------|-------|--------|
| Commands | {N} | {list names} |
| Agents | {N} | {list names} |
| CLAUDE.md | {Present/Missing} | |
| Knowledge bases | {N} | |

## Recent Activity

| Commit | Message |
|--------|---------|
| {hash} | {message} |

**Uncommitted changes:** {count} files

## Recommendations

1. **{Priority action}** — {reason and command to run}
2. **{Second action}** — {reason}
3. **{Third action}** — {reason}

## Suggested Commands

| Command | Reason |
|---------|--------|
| `/{command}` | {why relevant now} |
```

---

## Recommendation Logic

Generate recommendations based on:

| Condition | Recommendation |
|-----------|---------------|
| No KB files exist | "Run `/sql-kb <database>` to enable volume-aware PR reviews" |
| KB older than 30 days | "Run `/sql-kb --refresh <database>` — KB is {N} days stale" |
| Monitor stack not running | "Run `docker-compose -f monitor/docker-compose.yml up -d` to start monitoring" |
| No .env file for monitor | "Create `monitor/.env` with Grafana credentials — stack needs it to start" |
| CLAUDE.md missing | "Run `/sync-context` to generate CLAUDE.md" |
| Uncommitted changes | "Commit or stash {N} uncommitted files" |
| New scripts added without docs | "Add documentation for new scripts in the matching docs/ folder" |

---

## Best Practices

### When to Run

- Start of session to regain context
- Before sprint reviews or standups
- After adding new scripts or commands
- When onboarding someone to data-eyes
