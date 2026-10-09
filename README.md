<div align="center">
  <img src="assets/logo.png" alt="Data Eyes logo" width="180">
</div>

# Data Eyes

Data Eyes monitors a fleet of Microsoft SQL Servers. A Python **collector** runs fixed,
read-only queries on a schedule; **Prometheus** keeps 30 days of the results;
**Grafana** shows dashboards and sends alerts. An **MCP server** gives AI agents
(Claude Code and other MCP clients) the same fleet through 27 read-only tools. A Caddy
**gateway** puts everything behind one HTTPS port.

```text
                 instances.yaml (the fleet)
                  │                    │
                  ▼                    ▼
  collector ──/metrics──▶ Prometheus ──▶ Grafana ──┐
  (scheduled SQL,         (30 days)     (dashboards, │
   56 alert checks)          ▲           alerts)     │
                             │ history               ▼
  data-eyes-mcp ─────────────┘        gateway (Caddy, HTTPS :8443)
  (27 agent tools, live SQL) ◀──────── /mcp, /staging/mcp, /production/mcp
```

## Quick start

Requirements: Docker with Compose, and network access from Docker to your SQL Servers.

1. **Create the local config files.** They are ignored by Git.
   ```powershell
   Copy-Item .env.example .env
   Copy-Item instances.example.yaml instances.yaml
   Copy-Item mcp/.env.example mcp/.env
   ```
2. **Create a read-only SQL login** on each SQL Server (review the script first):
   ```powershell
   sqlcmd -S <server> -v LoginName="data_eyes_monitor" Password="<generated>" DatabaseName="master" SchemaName="dbo" -i mcp/sql/provision-readonly-login.sql
   ```
   [provision-alerting-permissions.sql](mcp/sql/provision-alerting-permissions.sql)
   adds the optional grants some alert checks need (msdb history, CommandLog,
   `VIEW ANY DEFINITION`). Each section says which alerts it enables.
3. **Fill in the config** as described in [Configuration](#configuration): your
   servers in `instances.yaml`, a strong `GRAFANA_ADMIN_PASSWORD` in `.env`, and the
   SQL logins in `mcp/.env`.
4. **Start the stack:**
   ```powershell
   docker compose up -d --build
   ```
5. **Open https://localhost:8443** and sign in to Grafana. The gateway uses its own
   local certificate authority, so trust its certificate according to your policy.
   Dashboards are in the **Data Eyes** folder.

Alerts are evaluated from the start but delivered nowhere until you configure a
contact point (see [Grafana](#grafana)).

## Configuration

Never commit or share these files. Reference variables by name, not value.

### `.env` (repository root)

| Variable | Required | Purpose |
|---|---|---|
| `GRAFANA_ADMIN_PASSWORD` | yes | Grafana admin password. Seeds an empty `grafana-data` volume only; change it later in Grafana. |
| `GRAFANA_ADMIN_USER` | no | Grafana admin user (default `admin`) |
| `DASHBOARD_HOST` | no | Hostname of the HTTPS site (default `localhost`) |
| `DASHBOARD_BIND_IP` | no | IP the gateway's port 8443 listens on (default `127.0.0.1`) |
| `DATA_EYES_ALERT_WEBHOOK_URL` | no | Webhook for the optional contact-point template |

### `instances.yaml`

One file describes the fleet for both the collector and the MCP server, plus the MCP
access grants:

```yaml
mcp_security:
  principals:
    production-agent:            # a name that MCP tokens map to
      tools: ["*"]               # fnmatch patterns over tool names
      instances: ["prod*"]       # fnmatch patterns over instance names

instances:
  - name: prod1                  # what tools and dashboards call it
    label: "Prod SQL Server 1"
    environment: production      # development | staging | production
    credential_env_prefix: PROD  # MCP reads PROD_MSSQL_USER / PROD_MSSQL_PASSWORD
    mssql_connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=prod1,1433;Encrypt=yes;TrustServerCertificate=no"
```

Both ODBC Driver 17 and 18 are installed in the images. The collector connects with
the credentials in the connection string. The MCP server replaces them with
`<PREFIX>_MSSQL_USER` / `<PREFIX>_MSSQL_PASSWORD` from `mcp/.env`, so agents can use a
narrower login than the collector.

### `mcp/.env`

| Variable | Purpose |
|---|---|
| `<PREFIX>_MSSQL_USER`, `<PREFIX>_MSSQL_PASSWORD` | SQL login per instance prefix (or `<PREFIX>_MSSQL_TRUSTED_CONNECTION=yes`). The server refuses to start without them. |
| `HTTP_TOKEN_HASHES` | JSON map of principal → SHA-256 hex digest of its bearer token. Required for HTTP. |
| `DEFAULT_PRINCIPAL` | Identity for stdio clients |
| `DEPLOYMENT_ENVIRONMENT`, `INSTANCE_ALLOWLIST` | Which instances this MCP server can see. Compose sets these per service. |
| `DEFAULT_INSTANCE`, `DEFAULT_DATABASE` | Defaults when a tool call omits them |
| `PROMETHEUS_URL` | Enables the history tools (Compose sets `http://prometheus:9090`) |
| `ALLOWED_HOST` | External hostname accepted by HTTP DNS-rebinding protection |
| `MSSQL_QUERY_TIMEOUT`, `MSSQL_CONNECTION_TIMEOUT`, `MAX_ROWS_PER_QUERY`, `MAX_RESPONSE_BYTES`, `MAX_CELL_LENGTH`, `MAX_CONCURRENT_QUERIES`, `RATE_LIMIT_PER_MINUTE` | Limits. Defaults: 30 s, 30 s, 50,000 rows, 2 MB, 4,000 characters, 8 queries, 60 calls/minute per principal. |

Per-environment overrides go in `mcp/.env.dev`, `mcp/.env.staging` and
`mcp/.env.production` (templates included).

## Services and ports

| Service | Port | Notes |
|---|---|---|
| `gateway` | `127.0.0.1:8443` (HTTPS) | Grafana at `/`, MCP dev at `/mcp`, staging at `/staging/mcp`, production at `/production/mcp` |
| `grafana` | internal 3000 | Reached through the gateway only |
| `prometheus` | internal 9090 | Scrapes the collector every 30 s, keeps 30 days |
| `collector` | internal 8090 | `/metrics`, `/health` |
| `data-eyes-mcp-dev` | `127.0.0.1:8080` | Always started |
| `data-eyes-mcp-staging` | `127.0.0.1:8081` | `docker compose --profile staging up -d` |
| `data-eyes-mcp-prod` | `127.0.0.1:8082` | `docker compose --profile production up -d` |

Each MCP service sees only its own environment's instances and credentials; Compose
blanks the other environments' passwords. Run exactly one collector per
`collector-state` volume.

## Collector

[collector/](collector) is a FastAPI app that queries each instance on its own
schedule and serves cached results at `/metrics`. Prometheus scrapes never trigger SQL.

- **Metric groups** every 30 s: resources, memory, I/O, waits, counters, activity;
  databases every 5 minutes.
- **56 alert checks** in 7 groups: Availability (9), Backup & integrity (7), Storage (8),
  Tempdb (4), Performance & activity (12), Maintenance (8), Configuration & security (8).
  Defaults live in [catalog.py](collector/app/alerts/catalog.py) and mirror
  `.claude/knowledge-base/_static/thresholds.yaml`. Override thresholds, exclusions, or
  per-instance settings in [checks.yaml](collector/checks.yaml) and restart the collector.
- **Severity** is exported as `data_eyes_health_severity{category="alert.<key>"}` and
  `data_eyes_overall_severity`: 0 OK, 1 Unknown, 2 Warning, 3 Critical.
- **Light on production:** separate concurrency lanes for slow checks, a 30-second
  query limit, and checks that time out back off for up to an hour instead of
  retrying every minute. Sessions are tagged `APP=Data Eyes Collector` for Resource
  Governor, and the image pools ODBC connections instead of logging in per query. See [collector/README.md](collector/README.md).

## Prometheus

[prometheus/prometheus.yml](prometheus/prometheus.yml) scrapes the collector every
30 seconds and keeps 30 days (`--storage.tsdb.retention.time=30d`). Three recording
rules compute batch requests per second, I/O bytes per second, and I/O latency.

## Grafana

Provisioned from [grafana/](grafana):

- **Dashboards:** Fleet, Instance, Database, and Health (collection freshness and failures).
- **Alert rules (6):** exporter unavailable, SQL Server unavailable, diagnostic
  unavailable or stale, SQL Server warning, SQL Server critical, SQL Server events detected.
- **Delivery:** configure a contact point in the Grafana UI, or set
  `DATA_EYES_ALERT_WEBHOOK_URL`, copy
  `grafana/provisioning/alerting/contact-points.yml.example` to `contact-points.yml`,
  and restart Grafana.

Sign-up and anonymous access are disabled; cookies are secure-only.

## MCP server

[mcp/](mcp) lets agents inspect the fleet with fixed, read-only tools. There is no
ad-hoc SQL.

| Group | Tools |
|---|---|
| Discovery | `list_configured_instances`, `list_databases`, `list_schemas`, `list_tables`, `describe_table`, `schema_discovery`, `get_relationships`, `sample_table`, `distinct_values`, `get_database_info`, `check_db_connection` |
| Diagnostics | `wait_stats`, `missing_indexes`, `unused_indexes`, `stale_statistics`, `index_fragmentation`, `top_queries`, `db_space`, `backup_health`, `checkdb_health`, `blocking_snapshot`, `ag_health`, `job_health`, `fleet_health_score` |
| History (Prometheus) | `list_tracked_instances`, `get_severity_trend`, `get_latest_snapshot` |

Every SQL tool takes an optional `instance`; most also take `database`. History tools
read the collector's severities from Prometheus; all other tools query SQL Server live.

### Connecting a client

- **Claude Code (stdio):** [.mcp.json](.mcp.json) already registers the server. It
  runs `uv --directory mcp run data-eyes-mcp` as `DEFAULT_PRINCIPAL=development-agent`
  against the `dev` instance.
- **HTTP:** create a token and its hash:
  ```powershell
  python -c "import secrets,hashlib;t=secrets.token_urlsafe(32);print(t);print(hashlib.sha256(t.encode()).hexdigest())"
  ```
  Add `{"<principal>":"<hash>"}` to `HTTP_TOKEN_HASHES`, restart the MCP service, and
  point the client at `https://<DASHBOARD_HOST>:8443/mcp` with
  `Authorization: Bearer <token>`.

### More SQL Servers

Add each server to `instances.yaml` with its own `credential_env_prefix`, set
`<PREFIX>_MSSQL_USER` and `<PREFIX>_MSSQL_PASSWORD` in `mcp/.env`, add the name to the
service's `INSTANCE_ALLOWLIST` (or leave the allowlist empty for every instance of that
environment), grant it to the principal, and restart. Then call tools with
`instance="<name>"`.

### Code

| File | Responsibility |
|---|---|
| [main.py](mcp/src/data_eyes_mcp/main.py) | CLI, logging with secret redaction, stdio or HTTP startup |
| [config.py](mcp/src/data_eyes_mcp/config.py) | Settings, `instances.yaml` (cached by modification time), startup validation |
| [auth.py](mcp/src/data_eyes_mcp/auth.py) | Bearer-token middleware, tool and instance grants, rate limit, audit log |
| [db.py](mcp/src/data_eyes_mcp/db.py) | Scoped-login connections, timeouts with cursor cancel, row/cell/byte caps |
| [output.py](mcp/src/data_eyes_mcp/output.py) | JSON envelope marking rows as untrusted database content |
| [queries.py](mcp/src/data_eyes_mcp/queries.py) | Diagnostic SQL and severity rules |
| [tools.py](mcp/src/data_eyes_mcp/tools.py) | All 27 tools behind one `@tool` decorator |

## Security

- **One HTTPS entry point.** Every published port binds to `127.0.0.1` by default;
  outside access goes through the gateway (HSTS, `X-Frame-Options DENY`, 128 KB request
  limit).
- **MCP authentication.** HTTP callers need a bearer token whose SHA-256 hash is in
  `HTTP_TOKEN_HASHES`; identity headers are ignored and only `/health` is public. Stdio
  uses `DEFAULT_PRINCIPAL`, and HTTP never falls back to it. Use long random tokens.
- **MCP authorization.** Each principal gets tool and instance grants; everything else
  is denied. Errors only list instances the caller is granted. Grants reload when
  `instances.yaml` changes; token changes need a restart.
- **SQL Server decides data access.** The MCP has no table- or column-level rules. Give
  each environment's MCP login read-only access to only what agents may see.
  `sample_table` and `distinct_values` return real rows, and `top_queries` and
  `blocking_snapshot` show query text and logins from every database (they need
  `VIEW SERVER STATE`).
- **Read-only by construction.** Only fixed statements run; user input reaches SQL
  Server only as bound parameters, quoted identifiers, or escaped literals. MCP
  transactions are never committed.
- **Limits and audit.** Timeouts, concurrency, row, cell, byte, and per-principal rate
  limits apply to every MCP call. Each call, denial, and error is logged as a
  `security_audit` JSON line, without query text. Passwords and connection strings are
  redacted from logs; connection strings are never returned to clients.
- **Prompt injection.** Results are labelled `untrusted_database_content`, and agents
  are told never to follow stored text.
- **CI.** [security.yml](.github/workflows/security.yml) runs the MCP tests,
  validates the Prometheus config, builds both images, audits dependencies with
  `pip-audit`, and scans for secrets with gitleaks.

## Claude Code toolkit

[.claude/](.claude) adds SQL Server DBA workflows for Claude Code:

- **Agents:** `sql-server-dba` (troubleshooting, tuning, maintenance; prefers live MCP
  tools over reading scripts) and `dashboard-app` (Grafana, Prometheus, collector, deployment).
- **Commands:** `/sql-performance`, `/sql-maintenance`, `/sql-scripts`, `/sql-monitor`,
  `/sql-document`, `/sql-kb`, `/sql-pr-review`, `/sql-guidelines`, `/sql-visual-report`,
  `/status`, `/sync-context`, `/memory`.
- **Resources:** performance queries and a tuning workbook, maintenance playbooks with
  Ola Hallengren use cases, and 84 copy-paste-safe scripts in 18 folders.
- **Knowledge base:** static thresholds, taxonomy, naming conventions, and methodology,
  plus per-database knowledge built by `/sql-kb`.

## Development

```powershell
cd collector; uv run python -c "import app.main"   # no test suite for now
cd mcp; uv run --extra dev pytest; uv run ruff check src tests
docker build -t data-eyes-mcp mcp
docker build -t data-eyes-collector collector
```

## Repository map

| Path | Contents |
|---|---|
| `collector/` | Scheduled SQL collection, alert checks, Prometheus exporter |
| `prometheus/` | Scrape config and recording rules |
| `grafana/` | Dashboards, data source, alert rules, contact-point template |
| `gateway/` | Caddy HTTPS reverse proxy |
| `mcp/` | MCP server, tests, SQL login provisioning scripts |
| `.claude/` | Agents, commands, knowledge base, SQL resources |
| `instances.example.yaml` | Fleet and MCP access template |
| `docker-compose.yml` | The whole stack, with staging and production MCP profiles |

Data Eyes is MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md).
