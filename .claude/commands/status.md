---
name: status
description: Data Eyes project health report — dashboard app, maintenance coverage, script inventory, KB freshness, and recommendations
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

1. **Scans** all toolkit components (dashboard/mcp, performance, maintenance, sql-scripts)
2. **Checks** dashboard app health (Docker containers, instance registry)
3. **Audits** knowledge base freshness and coverage
4. **Counts** script inventory across all 18 sub-folders
5. **Generates** actionable recommendations

---

## Execution Process

Execute all steps inline (no agent delegation).

### Step 1: Scan Toolkit Components

```text
# Dashboard app + MCP (agent-only, separate from the dashboard)
Glob("dashboard/docker-compose.yml")
Glob("dashboard/backend/instances.yaml")
Glob("mcp/docker-compose.yml")
Glob(".claude/knowledge-base/_static/*")

# Performance toolkit
Glob(".claude/resources/performance/additional_queries/*.sql")
Glob(".claude/resources/performance/additional_queries/docs/*.md")
Glob(".claude/resources/performance/performance_tuning_workbook.xlsx")

# Maintenance
Glob(".claude/resources/maintenance/*.sql")
Glob(".claude/resources/maintenance/use_cases/*.sql")

# SQL Scripts library
Glob(".claude/resources/sql-scripts/**/*.sql")
```

Count files in each component.

### Step 2: Check Dashboard App Health

```bash
# Check if Docker is available
docker --version 2>/dev/null || echo "Docker not installed"

# Check if the dashboard app is running (only if Docker available) — no
# no MCP container to check — the dashboard connects to SQL Server directly
docker compose -f dashboard/docker-compose.yml ps 2>/dev/null || echo "Dashboard stack not running"

# Check if .env exists for the dashboard backend
ls dashboard/backend/.env 2>/dev/null || echo "No .env file — dashboard backend will fail to start"
```

Read `dashboard/backend/instances.yaml` — count registered instances (names only, never credentials).

### Step 3: Audit Knowledge Base

```text
Glob(".claude/knowledge-base/*.md")
```

For each KB file found:
- Read first 10 lines to extract: Generated date, Server, EngineEdition, MajorVersion
- Calculate age in days from generated date
- Flag if older than 30 days

### Step 4: Script Inventory

Count `.sql` files per sub-folder in `.claude/resources/sql-scripts/`:

```text
Glob(".claude/resources/sql-scripts/audit/*.sql")
Glob(".claude/resources/sql-scripts/backup_recovery/**/*.sql")
Glob(".claude/resources/sql-scripts/custom_alert_emails/*.sql")
Glob(".claude/resources/sql-scripts/database_size/*.sql")
Glob(".claude/resources/sql-scripts/free_space/*.sql")
Glob(".claude/resources/sql-scripts/functions/*.sql")
Glob(".claude/resources/sql-scripts/helps/**/*.sql")
Glob(".claude/resources/sql-scripts/index/*.sql")
Glob(".claude/resources/sql-scripts/lock/*.sql")
Glob(".claude/resources/sql-scripts/query_store/*.sql")
Glob(".claude/resources/sql-scripts/server/*.sql")
Glob(".claude/resources/sql-scripts/sql_access/*.sql")
Glob(".claude/resources/sql-scripts/sql_agent/*.sql")
Glob(".claude/resources/sql-scripts/sql_profiler/*.sql")
Glob(".claude/resources/sql-scripts/ssis/*.sql")
Glob(".claude/resources/sql-scripts/ssrs/*.sql")
Glob(".claude/resources/sql-scripts/triggers/*.sql")
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
| Dashboard app | {N} instances registered | {Running/Stopped/Unknown} | `dashboard/` |
| Performance | {N} scripts, {N} docs, workbook | Present | 10-step methodology |
| Maintenance | {N} playbooks, {N} use cases | Present | Ola Hallengren |
| SQL Scripts | {N} scripts across {N} folders | Present | 18 topic areas |

## Dashboard App

| Check | Status |
|-------|--------|
| Docker installed | {Yes/No} |
| Dashboard stack running | {Yes/No/Unknown} |
| Dashboard backend .env file | {Present/Missing} |
| Instances registered | {N} — {names} |

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
| Dashboard stack not running | "Run `docker compose -f dashboard/docker-compose.yml up -d` to start the dashboard app" |
| No .env file for dashboard backend | "Copy `dashboard/backend/.env.example` to `.env` and set credentials — backend needs it to start" |
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
