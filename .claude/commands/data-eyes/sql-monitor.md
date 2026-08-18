---
name: sql-monitor
description: Data Eyes dashboard app — diagnose issues, explain tabs, manage the instance registry and user accounts
---

# /sql-monitor Command

> Diagnose and configure the Data Eyes dashboard app (`dashboard/`)

The old Grafana-based `monitor/` stack has been removed. This command targets its replacement: the custom `dashboard/` app, which connects directly to each monitored SQL Server — there's no MCP server in this path. `mcp/`'s `data-eyes-mcp` server is a separate, agent-only thing (Claude Code's `sql-server-dba` agent); it isn't part of the dashboard's own troubleshooting surface.

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
/sql-monitor "add a teammate a login"
/sql-monitor "restart the dashboard stack"
```

---

## What This Command Does

1. Reads the dashboard configuration at invocation time — configs are always the ground truth
2. Maps your issue or question to the right component (instance registry, backend/SQL Server connectivity, repository, insights agent, user accounts, or a specific tab)
3. Explains the fix, config change, or command needed
4. Shows exact `.env`-variable-name changes, API calls, or `docker compose` commands
5. Offers to run Docker commands after explicit user confirmation

This command is a thin front door onto the `dashboard-app` agent — for anything beyond a quick diagnosis, it delegates there.

---

## Stack Overview

```
┌──────────────────────────────────────────────────────┐
│  dashboard/                                           │
│  ├── docker-compose.yml                                │
│  │   ├── dashboard-repo    (Postgres — trend history,    │
│  │   │                      instance registry, users)     │
│  │   ├── dashboard-backend (FastAPI, :8090 — connects      │
│  │   │                      directly to each SQL Server)    │
│  │   └── dashboard-frontend (nginx, :8091)                   │
│  └── backend/instances.yaml — one-time seed for the           │
│      instance registry (not the live source of truth)          │
└──────────────────────────────────────────────────────┘
```

No MCP server, no `data-eyes-net` network dependency — the backend talks to SQL Server directly.

**Access:** Dashboard at `http://localhost:8091` (or wherever `dashboard-frontend` is exposed)
**Auth:** Real user accounts (`app_user` table) — `DASHBOARD_ADMIN_USERNAME`/`PASSWORD` only seed the first admin account, then accounts are managed via Manage Users / `POST /api/users`

---

## Process

### Step 1: Read Configuration

Always read these core files first:
```
Read("dashboard/backend/instances.yaml")
Read("dashboard/docker-compose.yml")
Read("dashboard/README.md")
```

For tab/metric questions, also read:
```
Read(".claude/knowledge-base/_static/taxonomy.md")   — category → tab → script → tool/function name
Read(".claude/knowledge-base/_static/thresholds.yaml") — severity bands
```

### Step 2: Map Problem to Category

| User says... | Focus on | Files to check |
|---|---|---|
| instance unreachable, unknown status, no data for a tab | SQL Server connectivity for that instance | the registered connection string (never display it — see below), backend logs for `MSSQLError` |
| won't start, container fails, port already in use | Docker Compose service config | `dashboard/docker-compose.yml` |
| trend strip says "unavailable", or login fails outright | Repository connectivity (now required, not optional) | `dashboard/backend/.env` → `REPOSITORY_DSN` (name only), `dashboard-repo` container health |
| insights feed empty, no "Explain in depth" output | Insights agent config | `dashboard/backend/.env` → `ANTHROPIC_API_KEY` (name only), backend logs |
| add/remove/rename an instance | Instance registry (a runtime API, not a file edit) | `GET/POST/PUT/DELETE /api/instances` — `instances.yaml` only matters before first boot ever |
| add/remove a teammate's login | User accounts | Manage Users UI / `POST/DELETE /api/users` (admin-only) |
| what does tab/panel X show, what's normal | Taxonomy + thresholds | `.claude/knowledge-base/_static/taxonomy.md`, `thresholds.yaml` |
| restart, start, stop, update stack | Docker Compose commands | `dashboard/docker-compose.yml` |

### Step 3: Output by Category

**Instance unreachable:**
- Confirm the instance is actually registered (`GET /api/instances`) before assuming a connectivity problem — a typo'd name looks identical to "unreachable"
- Check backend logs for the actual `MSSQLError` (connection refused vs. login failed vs. timeout point to different fixes)
- The stored connection string is encrypted and never returned by any API — if it's wrong, the fix is re-entering it (PUT /api/instances/{name}), not inspecting the database column
- Show the exact fix, ask confirmation before restarting anything

**Docker stack issues (won't start):**
- Read `dashboard/docker-compose.yml`, check port conflicts and `env_file` references
- Show the relevant commands:
  ```
  docker compose -f dashboard/docker-compose.yml logs dashboard-backend
  docker compose -f dashboard/docker-compose.yml restart dashboard-backend
  ```
- Ask confirmation before running any `docker compose` command

**Repository / login issues:**
- `REPOSITORY_DSN` and `INSTANCE_SECRET_KEY` are **required** — unlike `ANTHROPIC_API_KEY`, their absence is a real startup failure, not a graceful no-op. If either is unset, that's the fix, not a feature being intentionally off
- If set but still failing, check `dashboard-backend` logs for `RepositoryUnavailable` (which operation failed) or `DecryptionError` (`INSTANCE_SECRET_KEY` changed since instances were registered — not recoverable, only re-registering fixes it)

**Insights agent issues:**
- Confirm whether `ANTHROPIC_API_KEY` is set (variable name only — never display the value)
- Unset is a valid, intentional no-op state here — every insight endpoint degrades gracefully by design
- If set but not working, check `dashboard-backend` logs for the actual auth/rate-limit error

**Instance registry changes:**
- This is a runtime operation: `POST /api/instances` to add, `PUT /api/instances/{name}` to edit, `DELETE /api/instances/{name}` to remove — any logged-in user can do this (one shared team)
- Prefer walking the user through the Manage Instances UI over doing it on their behalf via curl
- `instances.yaml` only seeds the registry before the very first boot; editing it later does nothing

**User account changes:**
- New accounts: an existing admin via Manage Users (`/manage/users`) or `POST /api/users` — never handle a plaintext password beyond relaying what the user typed for that one request
- Locked-out user: they self-service at `/account` if they can still log in; otherwise only an admin can help (delete + recreate — there's no reset flow)

**Tab/metric questions:**
- Look up the category in `taxonomy.md`, read the linked source doc and the relevant band in `thresholds.yaml`
- Explain in plain language: what it measures, normal range, warning thresholds

**Docker commands (restart/stop/start):**
- Show the exact command first, explain what it will do, ask "Ready to run? (yes/no)"
- ONLY run after explicit "yes"

---

## Common Commands Reference

```bash
docker compose -f dashboard/docker-compose.yml up -d
docker compose -f dashboard/docker-compose.yml restart dashboard-backend
docker compose -f dashboard/docker-compose.yml logs -f dashboard-backend
docker compose -f dashboard/docker-compose.yml ps
```

---

## Important Rules

- NEVER display the contents of any `.env` file — it contains secrets (session key, repository password, encryption key, Anthropic API key)
  - Only reference variable names and explain what they control
- NEVER display a decrypted instance connection string or a plaintext user password, in any context
- `REPOSITORY_DSN` and `INSTANCE_SECRET_KEY` are required — treat their absence as a startup misconfiguration to fix, not a graceful-degradation case. An unset `ANTHROPIC_API_KEY` genuinely is a deliberate no-op state — confirm with the user whether the insights agent is actually meant to be enabled before treating it as broken.
- Always show the exact command (or API call) before running it; never run `docker compose` commands, or create/delete users/instances, silently
- For anything beyond a quick diagnosis, hand off to the `dashboard-app` agent
