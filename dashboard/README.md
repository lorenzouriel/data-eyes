# Data Eyes Dashboard

The custom monitoring dashboard that replaces `monitor/`'s Grafana stack — a Main Page summarizing every connected SQL Server instance with Healthy/Warning/Critical status, backed by the [`mcp/`](../mcp/) DBA diagnostic tools rather than direct SQL connections or Prometheus scraping.

Phases 1-5 of the rearchitecture are done: the backend, the fleet registry, basic auth, the Main Page, the per-database DPA-style tabbed drill-down, trend history, and the embedded insights agent. Rebrand visual polish + `monitor/` deprecation (Phase 6) is the one remaining phase.

## Architecture

```
dashboard/backend/    FastAPI — talks to each instance's data-eyes-mcp server over MCP streamable-HTTP,
                       rolls up severities into fleet-wide health, gates everything behind a login,
                       runs a background collector that writes trend snapshots.
dashboard/frontend/   React + TS + Vite — Main Page, per-database tabbed drill-down, trend strips,
                       embedded insight callouts and the insights feed.
dashboard/repository/ Schema for the dedicated trend-history Postgres DB (init.sql).
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

Dashboard at `http://localhost:8091` (frontend, nginx-served, proxies `/api/` to the backend). Backend directly at `http://localhost:8090` if needed. `docker-compose.yml`'s `dashboard-repo` service (Postgres) starts automatically as part of this — set `DASHBOARD_REPO_PASSWORD` in your shell environment before `up -d`, or accept the `change-me` default for local use only.

## Trend history

A dedicated repository database (`dashboard-repo`, Postgres — see `dashboard/repository/init.sql`) that the backend's collector (`app/collector.py`) writes to on a fixed interval (`COLLECTOR_INTERVAL_SECONDS`, default 60s), independent of whether anyone has the dashboard open. It **never** connects to a monitored SQL Server — matches how real DPA keeps its performance history in its own store, not inside the systems it watches.

Optional: leave `REPOSITORY_DSN` unset in `dashboard/backend/.env` to run without trend history — the collector simply doesn't start, and every trend strip in the UI renders an "unavailable" state instead of erroring. Local dev without Docker:

```bash
docker run -d --name data-eyes-dashboard-repo -p 5432:5432 \
  -e POSTGRES_DB=data_eyes_dashboard -e POSTGRES_USER=data_eyes -e POSTGRES_PASSWORD=change-me \
  -v "$(pwd)/repository/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  postgres:16-alpine
# then in dashboard/backend/.env:
REPOSITORY_DSN=postgresql://data_eyes:change-me@localhost:5432/data_eyes_dashboard
```

Retention is a flat window (`TREND_RETENTION_DAYS`, default 30) enforced by the collector pruning old rows — not a tiered hourly/daily rollup the way DPA does internally. A reasonable follow-up if raw-resolution retention needs to stretch much further.

## Embedded insights agent

Claude-generated commentary that lives inside the request/response cycle, not a bolted-on chat widget — it reuses the exact same MCP data a page already fetched (`app/routers/insights.py` calls the same `TAB_BUILDERS` functions the tab-data route uses) rather than issuing duplicate queries.

- **On page load / tab switch** (`GET /api/insights/fleet/stream`, `GET /api/insights/instances/:id/databases/:db/tabs/:tab/stream`): 1-3 sentence anomaly commentary, streamed over SSE, rendered as the callout at the top of the Main Page and each drill-down tab.
- **Background severity-change sweep** (`app/insights_sweep.py`): re-checks `fleet_health_score` for every instance on `INSIGHTS_SWEEP_INTERVAL_SECONDS` (default 600s) and generates a fresh insight **only when a category's severity actually changes** — not on every tick — to bound cost. Pushed into an in-memory feed (`GET /api/insights/feed`, capped at `INSIGHTS_FEED_MAX_SIZE`, default 50) shown on the Main Page. The first sweep after startup only records a baseline; it doesn't fire insights for it, to avoid a startup flood.
- **On-demand deep explanation** (`POST /api/insights/explain`, the "Explain in depth" button on each drill-down tab): the only path that uses the stronger model, gated behind explicit user action, optionally taking a free-text question.
- **Model tiering**: `claude-haiku-4-5` for routine polling/sweep commentary, `claude-opus-5` (with `effort: "medium"`) only for on-demand deep explanations — kept out of the automatic paths specifically to bound LLM spend.

Optional: leave `ANTHROPIC_API_KEY` unset in `dashboard/backend/.env` to run without it. Every insight endpoint degrades to an empty SSE stream (`event: done` with no text) instead of erroring, the feed stays empty, and the background sweep never starts — nothing else in the dashboard depends on this feature being configured.

```bash
# dashboard/backend/.env
ANTHROPIC_API_KEY=sk-ant-...
INSIGHTS_SWEEP_INTERVAL_SECONDS=600
INSIGHTS_FEED_MAX_SIZE=50
```

**Verification note**: the graceful-degradation path (unconfigured, and configured-with-an-invalid-key producing a real `anthropic.AuthenticationError`) has been tested end-to-end against the live FastAPI app — both cases return 200s and empty/`done`-only SSE streams rather than crashing. Generating an actual insight from a real, valid API key has not been — no working `ANTHROPIC_API_KEY` was available in the environment this was built in. Worth a real smoke test (a seeded severity change, a genuine "explain in depth" click) before trusting the commentary quality in production.

## Auth

A single shared admin credential behind a signed session cookie (`app/auth.py`) — not a user database or RBAC system. This exists specifically so the dashboard doesn't regress on Grafana's built-in admin login; it is not meant to scale to multi-user access control. Replace `app/auth.py` if that's ever needed.

## Health rollup

Every MCP diagnostic tool (`wait_stats`, `backup_health`, `checkdb_health`, `blocking_snapshot`, `ag_health`, `job_health`, `index_fragmentation`) returns a `severity` per row, computed in SQL from `.claude/knowledge-base/_static/thresholds.yaml`. `app/health_score.py` only aggregates those pre-computed severities (worst-of-category per instance, worst-of-instance for the fleet) — it does not define its own thresholds. This is the real evaluated alerting logic `monitor/` never had; its Grafana "alerting" was only a provisioned SMTP contact point with zero actual alert rules.
