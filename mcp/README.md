# Data Eyes MCP

> **Secondary service — agent-only tooling.** This is what Claude Code (and other MCP clients) use to query SQL Server directly during a session. It is not required to run the [dashboard](../README.md) — that's the primary service, and it talks to SQL Server on its own, without going through this server at all. Skip this folder unless you're setting up Claude Code (or another MCP client) against this toolkit.

The MCP (Model Context Protocol) layer of the [Data Eyes](../README.md) toolkit — a Python server that safely exposes SQL Server database and DBA-diagnostic capabilities to LLM clients (Claude Code's `sql-server-dba` agent, or any other MCP client).

This server is agent-only: the [`dashboard/`](../dashboard/) app queries SQL Server directly (`dashboard/backend/app/diagnostics.py`) rather than through this server — MCP's tool-calling/policy-gate machinery is overhead a trusted backend running fixed, known queries doesn't need. What this server *does* additionally expose to an agent is read access to the dashboard's own trend-history repository (see `REPOSITORY_DSN` below) — a capability the dashboard's own rendering path doesn't need (it talks to that database directly) but an interactive Claude Code session might.

- If you want a complete guide of how to use, [click here](/docs/HOW_TO_USE.md)!

## Quick Start
### 1. Install Dependencies
```bash
cd data-eyes/mcp
pip install -r requirements.txt

# or:
uv sync
```

### 2. Configure Database
Create `.env` file:
```bash
# For local SQL Server (Linux/Docker)
export MSSQL_CONNECTION_STRING="Driver={ODBC Driver 17 for SQL Server};Server=localhost,1433;Database=master;UID=sa;PWD=YourPassword123"

# Or for Windows Auth
export MSSQL_CONNECTION_STRING="Driver={ODBC Driver 17 for SQL Server};Server=localhost;Database=master;Trusted_Connection=yes"
```

### 3. Run the Server
```bash
# With stdio transport (for MCP clients)
python -m data_eyes_mcp.cli

# With custom settings
MSSQL_QUERY_TIMEOUT=60 READ_ONLY=true python -m data_eyes_mcp.cli --log-level DEBUG

# Or with HTTP transport
python -m data_eyes_mcp.cli --transport http --bind 0.0.0.0:8080

# Build and run
docker build -t data-eyes-mcp:latest .
docker run -e MSSQL_CONNECTION_STRING="..." data-eyes-mcp:latest

# Or with Docker Compose (HTTP transport, reads .env)
cp .env.example .env   # then edit connection string
docker compose up -d
```

### 4. Test with curl (HTTP mode)
```bash
# Health check
curl http://localhost:8080/health

# Readiness check
curl http://localhost:8080/ready

# Server info
curl http://localhost:8080/info

# Prometheus metrics
curl http://localhost:8080/metrics
```

## Available MCP Tools
The server exposes these tools to MCP clients:

### 1. `execute_sql(sql, format="table", timeout=None, max_rows=None)`
Execute SELECT queries (or write operations if enabled).
- `format`: `"table"`, `"json"` or `"csv"`.
- `timeout`: per-query timeout (seconds), overrides `MSSQL_QUERY_TIMEOUT` for slow queries.
- `max_rows`: per-query row cap, overrides `MAX_ROWS_PER_QUERY`.
```
Input: "SELECT TOP 10 * FROM users", format="json"
Output: JSON rows + summary; truncation is flagged explicitly.
        Write statements return the affected-row count.
```

### 2. `list_schemas()`
List all database schemas
```
Input: (none)
Output: Schema names list
```

### 3. `list_tables(schema, limit=200)`
List tables with optional schema filter
```
Input: schema="dbo", limit=100
Output: Table list with metadata
```

### 4. `schema_discovery(schema)`
Get full schema metadata (tables, columns, types)
```
Input: schema="dbo"
Output: JSON with detailed column info
```

### 5. `describe_table(table)`
Describe a single table: columns, types, nullability, primary keys, descriptions
```
Input: table="dbo.users"  (schema prefix optional)
Output: JSON column metadata for that one table
```

### 6. `get_database_info()`
Get server/database metadata
```
Input: (none)
Output: Database name, version, machine name
```

### 7. `get_policy_info()`
Get current security policy settings
```
Input: (none)
Output: Policy details (allowed operations, limits)
```

### 8. `check_db_connection()`
Health check for database connectivity
```
Input: (none)
Output: Connection status
```

### 9. `get_relationships(table, schema)`
List foreign-key relationships so an agent can build correct JOINs
```
Input: table="orders"  (optional; matches parent or referenced side)
Output: JSON of parent table.column -> referenced table.column
```

### 10. `sample_table(table, limit=5)`
Return a few example rows to reveal a table's data shape and typical values
```
Input: table="dbo.users", limit=5
Output: JSON rows (limit capped at 100)
```

### 11. `distinct_values(table, column, limit=20)`
Most frequent distinct values of a column, with counts — learn what to filter on
```
Input: table="dbo.orders", column="status"
Output: JSON list of {value, count}, most frequent first (limit capped at 200)
```

### 12. `list_databases()`
List the databases the connected login can access (for cross-database work)
```
Input: (none)
Output: JSON list of {name, database_id, state}
```

### Multiple databases
- All discovery tools (`list_schemas`, `list_tables`, `describe_table`,
  `schema_discovery`, `get_relationships`) and `execute_sql` accept a `database`
  argument to target a specific database — otherwise they use `DEFAULT_DATABASE`
  or the login's default. Discover options with `list_databases`.
- **Cross-database queries work in a single statement** via fully-qualified names
  (`[OtherDb].schema.table`), including JOINs across databases — no `USE` and no
  multi-statement needed (multi-statement input is rejected by policy).

The server also sends `instructions` to clients on connect, guiding agents to
discover (`list_databases` → `describe_table` / `get_relationships` / `sample_table`
/ `distinct_values`) before querying.

## DBA Diagnostic Tools

Beyond the generic tools above, `data_eyes_mcp/dba_tools.py` registers 11 more: `wait_stats`, `missing_indexes`, `unused_indexes`, `stale_statistics`, `index_fragmentation`, `top_queries`, `db_space`, `backup_health`, `checkdb_health`, `blocking_snapshot`, `ag_health`, `job_health`, plus the `fleet_health_score` rollup. Each mirrors a script in `.claude/resources/performance/additional_queries/` or `.claude/resources/maintenance/diagnostics/`, returns a `severity` (`OK`/`WARNING`/`CRITICAL`) per row driven by `.claude/knowledge-base/_static/thresholds.yaml`, and is documented in full via its own docstring (visible to any MCP client, including Claude Code) — see `.claude/knowledge-base/_static/taxonomy.md` for the category ↔ tool routing table.

## Dashboard Repository Trend Tools

3 more tools, in `data_eyes_mcp/repository_tools.py`, give an agent read access to the [`dashboard/`](../dashboard/) app's own trend-history repository (a Postgres database — never a monitored SQL Server) — a different question than the live-SQL tools above answer: "how has this looked over time" rather than "what does this look like right now." Optional: set `REPOSITORY_DSN` to enable them; all three report "not configured" (never an error) when it's unset.

### `list_tracked_instances()`
Every instance registered in the dashboard's instance registry.
```
Input: (none)
Output: JSON list of {name, label, environment}
```

### `get_severity_trend(instance_name, category, hours=24)`
Severity/metric history for one instance+category, as collected by the dashboard's background collector.
```
Input: instance_name="prod1", category="wait_stats", hours=24
Output: JSON list of {captured_at, severity, metric_value}, oldest first
```

### `get_latest_snapshot(instance_name)`
Most recent severity + headline metric per category for one instance, as of the dashboard's last collection cycle (may be stale by up to its collection interval — for the current moment, use the live-SQL tools instead).
```
Input: instance_name="prod1"
Output: JSON list of {category, severity, metric_value, captured_at}
```

## Security Features
✅ **Read-Only by Default**
- Only SELECT queries allowed unless explicitly enabled
- Writes require `ENABLE_WRITES=true` + `ADMIN_CONFIRM` token

✅ **SQL Injection Prevention**
- Parameterized queries via pyodbc
- Multi-statement query blocking
- Banned keyword detection (DROP, ALTER, EXEC, etc.)

✅ **Sensitive Data Protection**
- Automatic log redaction (passwords, connection strings)
- Query hashing for safe logging
- No credentials in response bodies

✅ **Resource Limits**
- Query timeouts (default 30s)
- Row limits (default 50,000 rows)
- Query length limits (50KB)
- Connection pool limits

✅ **Audit Trail**
- Structured logging with request metadata
- Query metrics and statistics
- Client ID tracking (when provided)

## Observability
### Prometheus Metrics
Available at `GET /metrics` (HTTP mode):
- `mssql_queries_executed_total` — Total queries by tool and status
- `mssql_queries_blocked_total` — Blocked queries by reason
- `mssql_query_duration_seconds` — Query latency histogram
- `mssql_query_rows_returned` — Result set size histogram
- `mssql_active_queries` — Currently executing queries
- `mssql_server_ready` — Server readiness (0/1)

### Structured Logs
All logs in JSON format (when `LOG_FORMAT=json`):
```json
{
  "timestamp": "2024-01-15T10:30:00.123456",
  "level": "INFO",
  "logger": "data_eyes_mcp.tools",
  "message": "Query allowed",
  "module": "tools",
  "function": "execute_sql",
  "line": 42
}
```

### Health Checks
- `GET /health` — Liveness probe (always 200)
- `GET /ready` — Readiness probe (200 if DB connected)

## Common Tasks
### Change Log Level
```bash
LOG_LEVEL=DEBUG python -m data_eyes_mcp.cli
```

### Enable Write Operations
```bash
ENABLE_WRITES=true ADMIN_CONFIRM=secret python -m data_eyes_mcp.cli
```
> The app-level `ENABLE_WRITES` switch is only the first line of defense. The
> ultimate authority is the permissions of the SQL login you connect as — see
> credential override below.

### Use a Specific SQL Login (credential override)
Each deployment can run under its own SQL login without editing the base
connection string. `MSSQL_USER` / `MSSQL_PASSWORD` take precedence over any
`UID`/`PWD` embedded in `MSSQL_CONNECTION_STRING`:
```bash
# Base string holds only driver/server/database; identity comes from these:
MSSQL_USER=reporting_ro MSSQL_PASSWORD=secret python -m data_eyes_mcp.cli
```
- `MSSQL_USER`, `MSSQL_PASSWORD` — override the SQL credentials (ideal for secrets).
- `MSSQL_TRUSTED_CONNECTION=true` — use Windows/Integrated auth instead (ignores user/password).

Because the connected login's own permissions govern access, connecting with a
read-only login enforces read-only **at the database level**, regardless of
`ENABLE_WRITES`. Conversely, allowing writes requires both `ENABLE_WRITES=true`
and a login that has write permission.

#### Per-request credentials (remote clients, HTTP transport)
A remote client can authenticate as **its own** SQL login for the duration of a
request by sending credentials as HTTP headers — no server reconfiguration, and
it overrides the server's default identity just for that client. Set them in the
MCP client config, e.g. `.mcp.json`:
```json
{
  "mcpServers": {
    "data-eyes-mcp": {
      "type": "http",
      "url": "http://your-host:8080/mcp",
      "headers": {
        "X-MSSQL-User": "your_login",
        "X-MSSQL-Password": "your_password"
      }
    }
  }
}
```
Headers (all optional): `X-MSSQL-User`, `X-MSSQL-Password`,
`X-MSSQL-Trusted-Connection` (`true`/`false`). When absent, the server's default
credentials are used. Precedence: request headers → server `MSSQL_USER`/… →
`UID`/`PWD` in `MSSQL_CONNECTION_STRING`.

**Non-ASCII values:** HTTP header values must be Latin-1, so a value containing
non-ASCII characters (e.g. an accented password) can't be sent raw. For those,
send the base64 of the UTF-8 value in the `-B64` variant of the header, which
takes precedence over the plain one:
`X-MSSQL-User-B64`, `X-MSSQL-Password-B64`. Example (encode the value):
`printf '%s' 'pÁsswŐrd' | base64`.

> Security: credentials travel in headers, so use HTTPS (or a trusted network).
> Access is still bounded by that login's own SQL Server permissions.

### Increase Query Timeout
```bash
MSSQL_QUERY_TIMEOUT=120 python -m data_eyes_mcp.cli
```

### Fix Garbled Non-ASCII Characters (accents, etc.)
Results are decoded using explicit encodings. The defaults work for most SQL Server
setups (NVARCHAR is UTF-16LE, VARCHAR is read as UTF-8). If `VARCHAR` columns use a
legacy code-page collation, override the narrow encoding:
```bash
# e.g. Central-European legacy VARCHAR data
MSSQL_ENCODING=cp1250 python -m data_eyes_mcp.cli
```
- `MSSQL_ENCODING` (default `utf-8`) — decoding of narrow `SQL_CHAR`/`VARCHAR` columns
- `MSSQL_WIDE_ENCODING` (default `utf-16-le`) — wide `SQL_WCHAR`/`NVARCHAR` decoding **and** the query/parameter send encoding (SQL Server expects UTF-16LE; sending UTF-8 corrupts accented literals in queries)

### Allow External Access (HTTP transport)
By default the server only accepts requests whose Host is `localhost` or
`127.0.0.1` (DNS rebinding protection). To allow access via an external
hostname, set `ALLOWED_HOST` to that host (without port):
```bash
ALLOWED_HOST=mcp.example.com python -m data_eyes_mcp.cli --transport http --bind 0.0.0.0:8080
```
This adds the host to both the allowed hosts and the CORS origins list; local
access keeps working.

### Run Multiple Instances
```bash
python -m data_eyes_mcp.cli --transport http --bind 127.0.0.1:8080
python -m data_eyes_mcp.cli --transport http --bind 127.0.0.1:8081  # Different port
```
