# Data Eyes Dashboard

The custom monitoring dashboard that replaces `monitor/`'s Grafana stack — a Main Page summarizing every connected SQL Server instance with Healthy/Warning/Critical status, per-database DPA-style drill-down, trend history, and an embedded insights agent.

The backend talks to each monitored SQL Server **directly** (`app/mssql_client.py`, `app/diagnostics.py`) — there's no MCP server in this path. MCP (see [`mcp/`](../mcp/)) is reserved for agent use: Claude Code's `sql-server-dba` agent, and an optional set of tools that let an agent query this dashboard's own trend history. See "Why not MCP for the dashboard itself?" below if you're wondering why that changed.

## Architecture

```
dashboard/backend/    FastAPI — connects directly to each instance's SQL Server,
                       rolls up severities into fleet-wide health, gates everything
                       behind real user accounts, runs a background collector that
                       writes trend snapshots, manages the instance registry.
dashboard/frontend/   React + TS + Vite — Main Page, per-database tabbed drill-down,
                       trend strips, embedded insight callouts, instance/user management.
dashboard/repository/ Schema for the dashboard's own Postgres DB (init.sql) — trend
                       history, the instance registry, and user accounts.
```

### Why not MCP for the dashboard itself?

Earlier versions of this dashboard routed every read — every fleet-health poll, every tab render, the trend collector — through a `data-eyes-mcp` server per instance, over the MCP protocol. That's the wrong tool for the job: MCP's tool-calling/policy-gate machinery exists to make arbitrary LLM-issued queries safe, which is real value for an agent but pure overhead for a trusted backend running its own fixed, known queries on every page load. It also required a 4-container "MCP fleet" (one per instance) that existed for no reason other than giving the dashboard a way to reach each SQL Server.

Now the backend queries SQL Server directly (`app/diagnostics.py` — a direct-SQL port of the same queries `mcp/`'s diagnostic tools run, same severity thresholds), and MCP is free to be what it's actually for: agent tool-calling. `mcp/` still exposes its full live-SQL diagnostic toolset unchanged, for Claude Code; it additionally exposes 3 tools (`list_tracked_instances`, `get_severity_trend`, `get_latest_snapshot`) that let an agent query *this dashboard's own trend history* — a capability the dashboard's rendering path doesn't need (it talks to its own repository directly, see `app/repository.py`) but an interactive agent session might.

## Quick start (local dev, no Docker)

### 1. Start Postgres (required — see "The dashboard's own database" below)

```bash
docker run -d --name data-eyes-dashboard-repo -p 5432:5432 \
  -e POSTGRES_DB=data_eyes_dashboard -e POSTGRES_USER=data_eyes -e POSTGRES_PASSWORD=change-me \
  -v "$(pwd)/repository/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  postgres:16-alpine
```

### 2. Backend

```bash
cd dashboard/backend
cp .env.example .env
# set DASHBOARD_ADMIN_PASSWORD, SESSION_SECRET_KEY, REPOSITORY_DSN, and
# INSTANCE_SECRET_KEY (generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
uv run --with-editable . uvicorn app.main:app --reload --port 8090
```

`instances.yaml` is a one-time seed for the database-backed instance registry — edit it before first boot, or just add instances through the UI afterward (see "Instance registry" below).

### 3. Frontend

```bash
cd dashboard/frontend
cp .env.example .env   # points at http://localhost:8090 by default
npm install
npm run dev             # http://localhost:5173
```

Sign in with `DASHBOARD_ADMIN_USERNAME`/`DASHBOARD_ADMIN_PASSWORD` — this only seeds the *first* admin account (see "User accounts" below).

## Running with Docker

```bash
docker compose -f dashboard/docker-compose.yml up -d
```

Dashboard at `http://localhost:8091` (frontend, nginx-served, proxies `/api/` to the backend). Backend directly at `http://localhost:8090` if needed. The `dashboard-repo` Postgres service starts automatically as part of this — set `DASHBOARD_REPO_PASSWORD` in your shell environment before `up -d`, or accept the `change-me` default for local use only.

If you also want Claude Code to have live SQL Server / trend-history access, run `mcp/` separately (`docker compose -f mcp/docker-compose.yml up -d`) — it's no longer something the dashboard depends on, so it's entirely optional and unrelated to getting the dashboard itself running.

## The dashboard's own database

A dedicated Postgres database (`dashboard-repo` — see `dashboard/repository/init.sql`) that the backend owns entirely. It **never** connects to a monitored SQL Server — matches how real DPA keeps its performance history in its own store, not inside the systems it watches. `REPOSITORY_DSN` is **required**: unlike the original trend-history-only design, this database now also backs the instance registry and user accounts, so the dashboard can't run at all without it (an earlier version of this doc described it as optional — that stopped being true once instances/users moved off static YAML/env-var config).

Three things live here:

- **Trend history** (`metric_snapshot` table) — the backend's collector (`app/collector.py`) writes a snapshot per instance on a fixed interval (`COLLECTOR_INTERVAL_SECONDS`, default 60s), independent of whether anyone has the dashboard open. Retention is a flat window (`TREND_RETENTION_DAYS`, default 30) enforced by the collector pruning old rows — not a tiered hourly/daily rollup the way DPA does internally. A reasonable follow-up if raw-resolution retention needs to stretch much further.
- **Instance registry** (`instance` table) — see below.
- **User accounts** (`app_user` table) — see below.

## Instance registry

`dashboard/backend/instances.yaml` is a **one-time seed**, not the live source of truth: on startup, any entry whose `name` isn't already registered gets inserted into the `instance` table, and the UI takes over from there (Manage Instances, linked from the Main Page topbar — any logged-in user can add/edit/remove instances, see "User accounts" for the tenancy model). Editing the YAML file after first boot has no effect on an instance that already exists.

Connection strings are encrypted at rest (`app/crypto.py`, Fernet, keyed by `INSTANCE_SECRET_KEY`) and never returned by the API — `GET /api/instances` only ever shows name/label/environment. Losing `INSTANCE_SECRET_KEY` means every stored connection string becomes undecryptable; back it up like any other secret.

## User accounts

Real accounts (`app_user` table, bcrypt-hashed passwords) replaced the single shared `DASHBOARD_ADMIN_USERNAME`/`PASSWORD` credential — those two env vars now only matter once, to seed the first `admin`-role account when the table is empty at startup. After that, an admin creates further accounts via Manage Users (`/manage/users`, admin-only) or `POST /api/users`; any user can change their own password at `/account`.

One shared team, not multi-tenant: every logged-in user — `admin` or `member` — sees and manages the *same* instance registry. `role` only gates user management itself (creating/deleting accounts); it doesn't scope which instances or data a user can see.

## Embedded insights agent

Claude-generated commentary that lives inside the request/response cycle, not a bolted-on chat widget — it reuses the exact same data a page already fetched (`app/routers/insights.py` calls the same `TAB_BUILDERS` functions the tab-data route uses, which now query SQL Server directly via `app/diagnostics.py`) rather than issuing duplicate queries.

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

## Health rollup

Every `app/diagnostics.py` function (`wait_stats`, `backup_health`, `checkdb_health`, `blocking_snapshot`, `ag_health`, `job_health`, `index_fragmentation`, ...) returns a `severity` per row, computed in SQL from `.claude/knowledge-base/_static/thresholds.yaml`. `app/health_score.py` only aggregates those pre-computed severities (worst-of-category per instance, worst-of-instance for the fleet) — it does not define its own thresholds. This is the real evaluated alerting logic `monitor/` never had; its Grafana "alerting" was only a provisioned SMTP contact point with zero actual alert rules.
