---
name: monitor
description: Grafana SQL Server monitoring stack — diagnose issues, explain dashboards, configure alerts
---

# /monitor Command

> Diagnose and configure the Grafana SQL Server monitoring stack

## Usage

```
/monitor <describe the issue or question>
```

## Examples

```
/monitor "Grafana is not showing any data"
/monitor "how do I add an email alert for buffer pool?"
/monitor "what does the Page Life Expectancy panel show?"
/monitor "the stack won't start — container error"
/monitor "restart the monitoring stack"
/monitor "how do I connect to a different SQL Server?"
/monitor "what metrics are available in the dashboard?"
/monitor "set up Gmail SMTP for alert notifications"
```

---

## What This Skill Does

1. Reads the monitoring stack configuration files at invocation time — configs are always the ground truth
2. Maps your issue or question to the right component (Docker, datasource, Grafana config, dashboard, alerts)
3. Explains the fix, config change, or command needed
4. Shows exact YAML/INI changes or `docker-compose` commands
5. Offers to run Docker commands after explicit user confirmation

---

## Stack Overview

The monitor stack runs as Docker containers:

```
┌─────────────────────────────────────────┐
│         monitor/                        │
├─────────────────────────────────────────┤
│  docker-compose.yml   → service defs    │
│  grafana/                               │
│  ├── grafana.ini      → Grafana config  │
│  ├── datasources.yml  → SQL Server conn │
│  ├── dashboard-provider.yml             │
│  ├── alerts-and-notifiers.yml           │
│  └── dashboards/                        │
│      ├── sqlserver.json  (comprehensive)│
│      └── sql_server_simplified.json     │
│  docs/                → panel docs      │
└─────────────────────────────────────────┘
```

**Access:** Grafana at `http://localhost:3000`
**Default credentials:** Set via `.env` file (GF_SECURITY_ADMIN_USER / GF_SECURITY_ADMIN_PASSWORD)

---

## Process

### Step 1: Read Monitor Configuration

Always read these core files first:
```
Read("monitor/docker-compose.yml")
Read("monitor/grafana/datasources.yml")
Read("monitor/grafana/grafana.ini")
Read("monitor/grafana/alerts-and-notifiers.yml")
Read("monitor/README.md")
```

For dashboard-related questions, also read:
```
Read("monitor/grafana/dashboards/sqlserver.json")       — comprehensive dashboard
Read("monitor/grafana/dashboards/sql_server_simplified.json") — simplified dashboard
Glob("monitor/docs/*.md") then Read matching doc files
```

### Step 2: Map Problem to Category

| User says... | Focus on | Files to check |
|---|---|---|
| not showing data, no metrics, empty panels, blank dashboard | SQL Server datasource connection | `datasources.yml` |
| won't start, container fails, port already in use, exit code | Service configuration, dependencies | `docker-compose.yml` |
| alert, email notification, SMTP, Gmail, alert channel | Alert notifier + SMTP config | `alerts-and-notifiers.yml` + `grafana.ini` |
| panel, dashboard, what does X mean, metric explanation | Panel documentation | matching `monitor/docs/*.md` |
| add panel, new metric, custom SQL query | Grafana JSON model, SQL datasource | `sqlserver.json` as reference |
| Azure SSO, Active Directory, authentication | Grafana auth config | `grafana.ini` — Azure SSO section |
| slow dashboard, refresh too fast/slow, performance | Refresh intervals, query optimization | `grafana.ini` + dashboard JSON |
| change SQL Server, different server, new connection | Datasource configuration | `datasources.yml` |
| restart, start, stop, update stack | Docker Compose commands | `docker-compose.yml` |

### Step 3: Output by Category

**Datasource issues (no data):**
- Read `datasources.yml` and identify the SQL Server connection parameters
- Check: server address, port, database, auth method, encrypted connection setting
- Show the exact YAML section that needs to change
- Explain: "Edit `monitor/grafana/datasources.yml`, then restart the Grafana container"
- Provide the restart command — ask confirmation before running

**Docker stack issues (won't start):**
- Read `docker-compose.yml` and identify service configuration
- Check: port conflicts (3000 for Grafana), volume mounts, env_file reference
- Show the relevant `docker-compose` commands:
  ```
  docker-compose -f monitor/docker-compose.yml logs grafana
  docker-compose -f monitor/docker-compose.yml down
  docker-compose -f monitor/docker-compose.yml up -d
  ```
- Ask confirmation before running any `docker-compose` command

**Alert/notification issues:**
- Read `alerts-and-notifiers.yml` and `grafana.ini`
- For Gmail SMTP: explain the required `grafana.ini` [smtp] section settings
- Show the exact INI/YAML changes needed
- Remind: changes to `grafana.ini` require a container restart
- Provide the restart command — ask confirmation before running

**Dashboard/panel questions:**
- Read the matching `monitor/docs/*.md` file for the panel topic
- Explain in plain language: what the metric measures, normal range, warning thresholds
- For "how do I add a panel": explain the Grafana JSON model structure
  - Important: Direct edits to `dashboards/*.json` are overwritten on container restart
  - Recommend: edit via Grafana UI, then export to replace the JSON file

**Docker commands (restart/stop/start):**
- Show the exact command first
- Explain what it will do
- Ask: "Ready to run? (yes/no)"
- ONLY run after explicit "yes"

---

## Common Commands Reference

```bash
# Start the stack
docker-compose -f monitor/docker-compose.yml up -d

# Stop the stack
docker-compose -f monitor/docker-compose.yml down

# Restart Grafana only (after config changes)
docker-compose -f monitor/docker-compose.yml restart grafana

# View Grafana logs
docker-compose -f monitor/docker-compose.yml logs -f grafana

# Check container status
docker-compose -f monitor/docker-compose.yml ps

# Force recreate (after docker-compose.yml changes)
docker-compose -f monitor/docker-compose.yml up -d --force-recreate
```

---

## Dashboard Panel Documentation Map

| Topic | Doc file |
|---|---|
| General overview, uptime, sessions, connections | `monitor/docs/general.md` |
| Buffer pool, index hit rate, PLE, memory grants | `monitor/docs/buffer_index_management.md` |
| Database file sizes, space usage, transaction log | `monitor/docs/database_space_usage.md` |
| SQL Agent jobs, execution status, failures | `monitor/docs/jobs_monitoring.md` |
| Top 10 slow queries, cache hit rate, latency | `monitor/docs/query_perfomance.md` |
| CPU, I/O, wait statistics | `monitor/docs/server_performance.md` |
| Locks, blocking, other metrics | `monitor/docs/other_metrics.md` |

---

## Important Rules

- NEVER display the contents of the `.env` file — it contains secrets
  - Only reference variable names (e.g., `GF_SECURITY_ADMIN_USER`) and explain what they control
- NEVER directly edit `monitor/grafana/dashboards/*.json` in production — changes are overwritten on container restart
  - For persistent dashboard changes: edit via Grafana UI → save → export JSON → replace the file
- Alert channel changes require restarting the Grafana container to take effect
- The stack uses `env_file: .env` — if `.env` doesn't exist, the containers will fail to start
- Always show the exact command before running it; never run `docker-compose` commands silently
