---
name: status
description: Data Eyes project health report — monitoring stack, maintenance coverage, script inventory, KB freshness, and recommendations
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

1. **Scans** all toolkit components (collector, Prometheus, Grafana, MCP, performance, maintenance, sql-scripts)
2. **Checks** monitoring stack health (Docker containers, fleet file, config files)
3. **Audits** knowledge base freshness and coverage
4. **Counts** script inventory across all 18 sub-folders
5. **Generates** actionable recommendations

---

## Execution Process

Execute all steps inline (no agent delegation).

### Step 1: Scan Toolkit Components

```text
# Monitoring stack + MCP (root docker-compose.yml runs all of them)
Glob("docker-compose.yml")
Glob("instances.yaml")                 # fleet file — ignored by Git
Glob("monitor/collector/app/**/*.py")
Glob("monitor/collector/checks.yaml")
Glob("monitor/prometheus/*.yml")
Glob("monitor/prometheus/rules/*.yml")
Glob("monitor/grafana/dashboards/*.json")
Glob("monitor/grafana/provisioning/**/*.yml")
Glob("mcp/src/data_eyes_mcp/*.py")
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

### Step 2: Check Monitoring Stack Health

```bash
# Check if Docker is available
docker --version 2>/dev/null || echo "Docker not installed"

# Service state for collector, prometheus, grafana, agent, data-eyes-mcp-*
docker compose ps 2>/dev/null || echo "Stack not running"

# Required env files (existence only — never print contents)
ls .env 2>/dev/null || echo "No root .env — Grafana will refuse to start (GRAFANA_ADMIN_PASSWORD is required)"
ls .env 2>/dev/null || echo "No .env — collector, Grafana and MCP will fail to start"
ls instances.yaml 2>/dev/null || echo "No instances.yaml — copy instances.example.yaml"
```

Read `instances.yaml` — count instances and list `name`/`environment` only. Never display `mssql_connection_string` values or anything under `mcp_security`.

If the stack is running, the collector's health is reachable only inside Compose:
```bash
docker compose exec collector python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8090/health').status)"
```

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
Glob(".claude/commands/*.md")

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
| Monitoring stack | {N} instances, {N} Grafana dashboards, {N} alert rules | {Running/Stopped/Unknown} | collector → Prometheus → Grafana |
| MCP | {N} tool modules | {Running/Stopped/Unknown} | `mcp/`, dev + optional staging/prod |
| Performance | {N} scripts, {N} docs, workbook | Present | 10-step methodology |
| Maintenance | {N} playbooks, {N} use cases | Present | Ola Hallengren |
| SQL Scripts | {N} scripts across {N} folders | Present | 18 topic areas |

## Monitoring Stack

| Check | Status |
|-------|--------|
| Docker installed | {Yes/No} |
| Services running | {collector / prometheus / grafana / agent / mcp-dev: Up/Down} |
| Root .env | {Present/Missing} |
| .env | {Present/Missing} |
| instances.yaml | {N} instances — {names (environment)} |
| Check overrides (`monitor/collector/checks.yaml`) | {N} rows |
| Collector /health | {OK/Failed/Not checked} |

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
| Stack not running | "Run `docker compose up -d` from the repository root" |
| Root `.env` missing | "Copy `.env.example` to `.env` and set `GRAFANA_ADMIN_PASSWORD` — Grafana requires it" |
| `.env` missing | "Copy `.env.example` to `.env` and set `GF_SECURITY_ADMIN_PASSWORD`" |
| `instances.yaml` missing | "Copy `instances.example.yaml` to `instances.yaml` and fill in the fleet locally" |
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
