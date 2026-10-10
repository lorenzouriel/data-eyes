---
name: sql-monitor
description: Data Eyes monitoring stack — diagnose collector, Prometheus, and Grafana issues, explain dashboards and alerts, manage the fleet file
---

# /sql-monitor Command

> Diagnose and configure the Data Eyes monitoring stack (collector → Prometheus → Grafana, all under `monitor/`)

## Usage

```
/sql-monitor <describe the issue or question>
```

## Examples

```
/sql-monitor "Grafana shows prod as unreachable"
/sql-monitor "the Fleet dashboard is empty / says No data"
/sql-monitor "backup health shows Unknown for staging"
/sql-monitor "add our new reporting replica to the fleet"
/sql-monitor "raise the CPU warning threshold to 85% on dev"
/sql-monitor "the collector container keeps restarting"
/sql-monitor "what does 'Seconds since successful collection' on the Health dashboard mean?"
/sql-monitor "add a teammate a Grafana login"
/sql-monitor "send critical alerts to our Teams channel"
/sql-monitor "restart the stack"
```

---

## What This Command Does

1. Reads the stack configuration at invocation time — configs are always the ground truth
2. Maps your issue or question to the right component (fleet file, collector, Prometheus, Grafana dashboards/alerts/users, or MCP)
3. Explains the fix, config change, or command needed
4. Shows exact YAML edits, `.env` variable names, PromQL, or `docker compose` commands
5. Offers to run Docker commands after explicit user confirmation

This command is a thin front door onto the `dashboard-app` agent — for anything beyond a quick diagnosis, it delegates there.

---

## Stack Overview

```
instances.yaml ──► collector (:8090 internal) ──/metrics──► Prometheus (:9090 internal, 30d)
       │              │  fixed read-only DMV queries            │
       │              ▼                                         ▼
       │         SQL Server fleet ◄──── data-eyes-mcp ───► Grafana (http://<GRAFANA_BIND_IP>:3000)
       └──────────────────────────────►  (dev/staging/prod,     UI + alerting
                                          127.0.0.1:8080-8082)
```

| Service | Config | Role |
|---|---|---|
| `collector` | `instances.yaml`, `monitor/collector/checks.yaml`, volume `collector-state` | Runs fixed diagnostics on a schedule, caches results, serves `/metrics` and `/health`. Scrapes never trigger SQL. One collector per checkpoint volume. |
| `prometheus` | `monitor/prometheus/prometheus.yml`, `monitor/prometheus/rules/recording.yml` | Scrapes `collector:8090` every 30s, keeps 30 days, computes rates from counters. |
| `grafana` | `monitor/grafana/grafana.ini`, `monitor/grafana/provisioning/`, `monitor/grafana/dashboards/`, `.env` (`GRAFANA_BIND_IP`, `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`, SMTP) | The UI: Fleet Overview (home page: fleet, instance, alerts, collector) ; Prometheus is its only datasource; alert rules, contact point, notification policy; human accounts (embedded SQLite). |
| `data-eyes-mcp-*` | `instances.yaml` (instances, `mcp_security` grants and `token_sha256`) | Agent tools. Reads history from Prometheus via `PROMETHEUS_URL`. Staging/prod are Compose profiles. |

**Access:** Grafana at `http://<GRAFANA_BIND_IP>:3000` (default `http://localhost:3000`). There is no TLS proxy in the stack; put one in front before exposing it beyond localhost.
**Auth:** Grafana accounts. `GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD` (in `.env`) create the admin on first start only; later changes need `grafana cli admin reset-admin-password`. Grafana data-source access is **not** a per-instance boundary — anyone who can query Prometheus sees the whole fleet.

---

## Process

### Step 1: Read Configuration

Always read these first:
```
Read("docker-compose.yml")
Read("docs/architecture/architecture.md")
Read("docs/features/metrics.md")              — metric names, labels, severity codes
Read("monitor/collector/checks.yaml")
```

For `instances.yaml`, read **only names, labels, and environments** — never echo `mssql_connection_string` values or `mcp_security` tokens.

For dashboard/alert/threshold questions, also read:
```
Read("docs/features/alerts.md")                       — check catalog, units, cadence
Read("monitor/grafana/provisioning/alerting/data-eyes-alerts.yml")
Read(".claude/knowledge-base/_static/taxonomy.md")     — category → dashboard → script → tool name
Read(".claude/knowledge-base/_static/thresholds.yaml") — severity bands and alert defaults
```

### Step 2: Map Problem to Category

| User says... | Focus on | Files / signals to check |
|---|---|---|
| instance unreachable, red on Fleet | SQL connectivity from the collector | `data_eyes_sqlserver_reachable{sql_instance="..."}`, `docker compose logs collector` |
| "No data" everywhere | Exporter or scrape | Health dashboard → *Exporter reachable*; Prometheus target `data-eyes`; collector `/health` |
| one category Unknown / stale | A single diagnostic failing or slow | `data_eyes_collection_success`, `data_eyes_collection_last_success_timestamp_seconds` by `collector` label; collector logs for permission/timeout errors |
| add/remove/rename an instance | Fleet file | `instances.yaml` → restart `collector` and the MCP service(s) |
| change a threshold or exclude a check | Check overrides | `monitor/collector/checks.yaml` (empty `instance_name` = fleet-wide) → restart `collector` |
| alerts not firing / not delivered | Grafana alerting | `monitor/grafana/provisioning/alerting/data-eyes-alerts.yml` (rules), `contact-points.yml` (email contact point and policy), SMTP settings in `.env` (names only) |
| add/remove a teammate's login | Grafana users | Grafana → Administration → Users (admin only) |
| what does panel X show, what's normal | Metric contract + thresholds | `docs/features/metrics.md`, `taxonomy.md`, `thresholds.yaml` |
| can't reach Grafana | Port binding | `GRAFANA_BIND_IP` in root `.env`, `docker compose ps grafana` |
| want MCP call metrics on the Health dashboard | Optional MCP scrape | `monitor/prometheus/mcp-scrape.example.yml`, `docs/getting-started/deployment.md` |
| restart, start, stop, update stack | Docker Compose | root `docker-compose.yml` |

### Step 3: Output by Category

**Instance unreachable:**
- Confirm the `name` exists in `instances.yaml` and matches the `sql_instance` label — a typo looks identical to "unreachable"
- Check collector logs for the actual driver error (connection refused vs. login failed vs. timeout vs. TLS/certificate point to different fixes)
- If the connection string is wrong, the fix is editing `instances.yaml` locally (never display it) and restarting `collector`
- Collector-wide limits (`SQL_MAX_CONCURRENT_QUERIES`, `SQL_MAX_BACKGROUND_QUERIES`, timeouts, `SQL_APPLICATION_NAME`) are env settings — reference names only

**Unknown / stale diagnostics:**
- Unknown (severity 1) means the measurement failed or is stale — the collector omits values instead of reporting zero
- Checks run at different cadences (fast 60s, standard 5 min, slow 1h, daily 24h; connection probe 30s) — check the key's cadence in `docs/features/alerts.md` before calling it stale
- Missing permissions are the usual cause — compare with `mcp/sql/provision-readonly-login.sql` and `provision-alerting-permissions.sql`

**Fleet and threshold changes:**
- Fleet: edit `instances.yaml`, then restart `collector` and the matching `data-eyes-mcp-*` service. There is no runtime registry API.
- Thresholds: add a row to `monitor/collector/checks.yaml` (`alert_key`, `instance_name`, and any of `enabled`, `warning_threshold`, `critical_threshold`, `tier`, `confirm_samples`, `excluded_databases`; null fields inherit fleet-wide then catalog values); warning must be below critical for `above` checks and above it for `below` checks. Restart `collector`.
- Catalog defaults change only in `.claude/knowledge-base/_static/thresholds.yaml` + `monitor/collector/app/alerts/catalog.py` together.

**Alerts and notifications:**
- Rules are provisioned from Git (`monitor/grafana/provisioning/alerting/data-eyes-alerts.yml`, folder "Data Eyes"): exporter down, SQL Server unavailable, diagnostic failing, warning, critical, events. There is no Alertmanager; Grafana evaluates and delivers
- Grafana alerts are time-window evaluations, not one notification per event; configure digests and escalation in Grafana notification policies or your incident tool
- Never send a test notification without explicit user authorization

**Grafana users:**
- Admin creates/removes users in the Grafana UI; never handle a plaintext password beyond relaying what the user typed for that one action
- Dashboard variables are filters, not authorization. Isolated tenants need separate stacks.

**Dashboard/metric questions:**
- Map the panel to its metric in `docs/features/metrics.md` (severity: 0 OK, 1 Unknown, 2 Warning, 3 Critical)
- Explain in plain language: what it measures, normal range, warning thresholds
- For "why is it high right now", hand over to the `sql-server-dba` agent and live MCP tools — Prometheus has numbers, not SQL text, plans, or sessions

**Docker commands (restart/stop/start):**
- Show the exact command first, explain what it will do, ask "Ready to run? (yes/no)"
- ONLY run after explicit "yes"

---

## Common Commands Reference

```bash
docker compose up -d
docker compose ps
docker compose logs -f collector
docker compose restart collector
docker compose restart prometheus grafana
docker compose --profile staging --profile production up -d   # optional MCP environments
```

---

## Important Rules

- NEVER display the contents of any `.env` file or `instances.yaml` connection strings — only reference variable/field names and explain what they control
- NEVER display bearer tokens, token hashes, or Grafana passwords
- Always show the exact command or file edit before applying it; never run `docker compose` commands silently
- Preserve the `prometheus-data`, `grafana-data`, and `collector-state` volumes; never delete them as a "fix"
- Run exactly one collector per `collector-state` volume — a second collector duplicates SQL load and events
- For anything beyond a quick diagnosis, hand off to the `dashboard-app` agent
