---
name: sql-monitor
description: Data Eyes dashboard app + MCP fleet — diagnose issues, explain tabs, configure the fleet registry
---

# /sql-monitor Command

> Diagnose and configure the Data Eyes dashboard app (`dashboard/`) and the MCP fleet it depends on (`mcp/`)

`monitor/`'s Grafana stack is deprecated — see `monitor/README.md`. This command now targets its replacement: the custom `dashboard/` app plus the `data-eyes-mcp` servers in `mcp/`.

## Usage

```
/sql-monitor <describe the issue or question>
```

## Examples

```
/sql-monitor "the dashboard says prod1 is unreachable"
/sql-monitor "trend strips show 'unavailable' — is the repository down?"
/sql-monitor "insights feed is empty, is that expected?"
/sql-monitor "add our new reporting replica to the fleet"
/sql-monitor "the dashboard-backend container won't start"
/sql-monitor "what does the Wait Time Analysis tab show?"
/sql-monitor "restart the dashboard stack"
```

---

## What This Command Does

1. Reads the dashboard/MCP configuration at invocation time — configs are always the ground truth
2. Maps your issue or question to the right component (fleet registry, MCP connectivity, backend, repository, insights agent, or a specific tab)
3. Explains the fix, config change, or command needed
4. Shows exact YAML/`.env`-variable-name changes or `docker compose` commands
5. Offers to run Docker commands after explicit user confirmation

This command is a thin front door onto the `dashboard-app` agent — for anything beyond a quick diagnosis, it delegates there.

---

## Stack Overview

```
┌───────────────────────────────────────────────────────────┐
│                     data-eyes-net (Docker network)         │
│                                                             │
│  dashboard/                          mcp/                  │
│  ├── docker-compose.yml              ├── docker-compose.yml (single instance)
│  │   ├── dashboard-repo   (Postgres, trend history)         │
│  │   ├── dashboard-backend (FastAPI, :8090)                 │
│  │   └── dashboard-frontend (nginx, :8091)                  │
│  └── backend/instances.yaml — fleet registry                └── docker-compose.fleet.yml
│      (name → mcp_url per instance)                              (data-eyes-mcp-dev/staging/prod1/prod2, :8081-8084)
└───────────────────────────────────────────────────────────┘
```

**Access:** Dashboard at `http://localhost:8091` (or wherever `dashboard-frontend` is exposed)
**Auth:** Single admin credential — set via `dashboard/backend/.env` (`DASHBOARD_ADMIN_USERNAME` / `DASHBOARD_ADMIN_PASSWORD`)

---

## Process

### Step 1: Read Configuration

Always read these core files first:
```
Read("dashboard/backend/instances.yaml")
Read("dashboard/docker-compose.yml")
Read("mcp/docker-compose.fleet.yml")
Read("dashboard/README.md")
```

For tab/metric questions, also read:
```
Read(".claude/knowledge-base/_static/taxonomy.md")   — category → tab → script → MCP tool
Read(".claude/knowledge-base/_static/thresholds.yaml") — severity bands
```

### Step 2: Map Problem to Category

| User says... | Focus on | Files to check |
|---|---|---|
| instance unreachable, unknown status, no data for a tab | MCP connectivity for that instance | `instances.yaml`, the matching `data-eyes-mcp-*` container, `data-eyes-net` network |
| won't start, container fails, port already in use | Docker Compose service config | `dashboard/docker-compose.yml`, `mcp/docker-compose.fleet.yml` |
| trend strip says "unavailable" | Repository connectivity | `dashboard/backend/.env` → `REPOSITORY_DSN` (name only), `dashboard-repo` container health |
| insights feed empty, no "Explain in depth" output | Insights agent config | `dashboard/backend/.env` → `ANTHROPIC_API_KEY` (name only), backend logs |
| add/remove/rename an instance | Fleet registry | `instances.yaml` + `mcp/docker-compose.fleet.yml` + `.env.<name>` |
| what does tab/panel X show, what's normal | Taxonomy + thresholds | `.claude/knowledge-base/_static/taxonomy.md`, `thresholds.yaml` |
| restart, start, stop, update stack | Docker Compose commands | both compose files |

### Step 3: Output by Category

**Instance unreachable:**
- Read `instances.yaml`, confirm the instance's `mcp_url` matches a running `data-eyes-mcp-*` container
- Check `docker network ls` includes `data-eyes-net` and both stacks joined it
- Show the exact fix, ask confirmation before restarting anything

**Docker stack issues (won't start):**
- Read the relevant compose file, check port conflicts and `env_file` references
- Show the relevant commands:
  ```
  docker compose -f mcp/docker-compose.fleet.yml logs data-eyes-mcp-<name>
  docker compose -f dashboard/docker-compose.yml logs dashboard-backend
  docker compose -f dashboard/docker-compose.yml restart dashboard-backend
  ```
- Ask confirmation before running any `docker compose` command

**Trend history / insights agent:**
- Confirm whether `REPOSITORY_DSN` / `ANTHROPIC_API_KEY` are set (variable names only — never display values)
- Unset is a valid, intentional no-op state, not a bug — both features degrade gracefully by design
- If set but not working, check `dashboard-backend` logs for the actual connection/auth error

**Fleet registry changes:**
- For a new instance: add a service to `mcp/docker-compose.fleet.yml` (copy the `x-mcp-service` anchor, next free port) and a `.env.<name>` file, plus a matching `instances.yaml` entry
- Show the full diff, ask confirmation, then offer the `docker compose up -d` commands

**Tab/metric questions:**
- Look up the category in `taxonomy.md`, read the linked source doc and the relevant band in `thresholds.yaml`
- Explain in plain language: what it measures, normal range, warning thresholds

**Docker commands (restart/stop/start):**
- Show the exact command first, explain what it will do, ask "Ready to run? (yes/no)"
- ONLY run after explicit "yes"

---

## Common Commands Reference

```bash
# One-time, before either stack
docker network create data-eyes-net

# MCP fleet
docker compose -f mcp/docker-compose.fleet.yml up -d
docker compose -f mcp/docker-compose.fleet.yml ps
docker compose -f mcp/docker-compose.fleet.yml logs -f data-eyes-mcp-prod1

# Dashboard app
docker compose -f dashboard/docker-compose.yml up -d
docker compose -f dashboard/docker-compose.yml restart dashboard-backend
docker compose -f dashboard/docker-compose.yml logs -f dashboard-backend
docker compose -f dashboard/docker-compose.yml ps
```

---

## Important Rules

- NEVER display the contents of any `.env` file — it contains secrets (SQL Server credentials, session key, repository password, Anthropic API key)
  - Only reference variable names and explain what they control
- An unset `REPOSITORY_DSN` or `ANTHROPIC_API_KEY` is a deliberate graceful-degradation state — confirm with the user whether the feature is actually meant to be enabled before treating it as broken
- Always show the exact command before running it; never run `docker compose` commands silently
- For anything beyond a quick diagnosis, hand off to the `dashboard-app` agent
