# Data Eyes Dashboard

The custom monitoring dashboard that replaces `monitor/`'s Grafana stack — a Main Page summarizing every connected SQL Server instance with Healthy/Warning/Critical status, backed by the [`mcp/`](../mcp/) DBA diagnostic tools rather than direct SQL connections or Prometheus scraping.

This is Phase 2 of the rearchitecture: the backend, the fleet registry, basic auth, and the Main Page (fleet cards + health badges). Per-database DPA-style tabbed drill-down, historical trend charts, and the embedded insights agent are later phases — not here yet.

## Architecture

```
dashboard/backend/   FastAPI — talks to each instance's data-eyes-mcp server over MCP streamable-HTTP,
                      rolls up severities into fleet-wide health, gates everything behind a login.
dashboard/frontend/  React + TS + Vite — Main Page: fleet cards with status badges, polling every 30s.
```

The backend never connects to SQL Server directly — every read goes through a `data-eyes-mcp` server (see [`mcp/`](../mcp/)), which already owns connection pooling, credentials, and the read-only policy gate. One `data-eyes-mcp` container per monitored instance (see `mcp/docker-compose.fleet.yml`), matching the same Dev/Staging/Prod1-AG/Prod2-AG topology `monitor/`'s Grafana datasources used.

## Quick start (local dev, no Docker)

### 1. Start an MCP server to point the dashboard at

Either the default single-instance one (`mcp/docker-compose.yml` / `python -m data_eyes_mcp.cli --transport http`), or the full fleet (`mcp/docker-compose.fleet.yml`, see below). Update `dashboard/backend/instances.yaml` to match whatever you're actually running — the shipped file assumes the fleet topology.

### 2. Backend

```bash
cd dashboard/backend
cp .env.example .env   # set DASHBOARD_ADMIN_PASSWORD and SESSION_SECRET_KEY
uv run --with-editable . uvicorn app.main:app --reload --port 8090
```

### 3. Frontend

```bash
cd dashboard/frontend
cp .env.example .env   # points at http://localhost:8090 by default
npm install
npm run dev             # http://localhost:5173
```

Sign in with the username/password from `dashboard/backend/.env`.

## Running the full fleet with Docker

```bash
docker network create data-eyes-net

# One data-eyes-mcp container per instance — copy mcp/.env.example to
# mcp/.env.dev, .env.staging, .env.prod1, .env.prod2 first.
docker compose -f mcp/docker-compose.fleet.yml up -d

docker compose -f dashboard/docker-compose.yml up -d
```

Dashboard at `http://localhost:8091` (frontend, nginx-served, proxies `/api/` to the backend). Backend directly at `http://localhost:8090` if needed.

## Auth

A single shared admin credential behind a signed session cookie (`app/auth.py`) — not a user database or RBAC system. This exists specifically so the dashboard doesn't regress on Grafana's built-in admin login; it is not meant to scale to multi-user access control. Replace `app/auth.py` if that's ever needed.

## Health rollup

Every MCP diagnostic tool (`wait_stats`, `backup_health`, `checkdb_health`, `blocking_snapshot`, `ag_health`, `job_health`, `index_fragmentation`) returns a `severity` per row, computed in SQL from `.claude/knowledge-base/_static/thresholds.yaml`. `app/health_score.py` only aggregates those pre-computed severities (worst-of-category per instance, worst-of-instance for the fleet) — it does not define its own thresholds. This is the real evaluated alerting logic `monitor/` never had; its Grafana "alerting" was only a provisioned SMTP contact point with zero actual alert rules.
