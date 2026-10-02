> **Security upgrade:** Read the [setup and migration guide](security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# MCP server

The Data Eyes MCP server is the agent-facing interface to the configured SQL
Server fleet. It exposes database exploration, DBA diagnostics, and dashboard
history as Model Context Protocol tools.

Source: [`src/mcp/`](../src/mcp/)

## How it fits into Data Eyes

MCP reads `src/instances.yaml` directly and selects a SQL Server by the
optional `instance` argument accepted by live tools. It does not call the
dashboard backend for live data. Repository tools connect read-only to the same
PostgreSQL history store used by the dashboard.

Call `list_configured_instances` before other tools when the available fleet or
default instance is unknown.

## Tool groups

### Fleet and SQL exploration

| Tool | Purpose |
|---|---|
| `list_configured_instances` | Lists YAML-defined instances without exposing credentials |
| `check_db_connection` | Tests the selected SQL Server connection |
| `execute_sql` | Disabled; use fixed diagnostic/discovery tools |
| `list_databases` | Lists accessible databases |
| `list_schemas` | Lists schemas in a database |
| `list_tables` | Lists tables with optional schema filtering |
| `schema_discovery` | Returns broader schema metadata |
| `describe_table` | Describes columns and metadata for one table |
| `get_relationships` | Discovers foreign-key relationships |
| `sample_table` | Returns a small bounded sample |
| `distinct_values` | Returns bounded distinct values for a column |
| `get_database_info` | Returns server and database metadata |
| `get_policy_info` | Describes the active query policy |

### DBA diagnostics

| Tool | Purpose |
|---|---|
| `fleet_health_score` | Evaluates the main health categories |
| `wait_stats` | Reports meaningful wait statistics |
| `blocking_snapshot` | Captures current blocking chains |
| `top_queries` | Identifies resource-intensive statements |
| `missing_indexes` | Returns SQL Server missing-index candidates |
| `unused_indexes` | Finds indexes with low read benefit and write cost |
| `stale_statistics` | Identifies old or modified statistics |
| `index_fragmentation` | Reports fragmentation above a threshold |
| `db_space` | Reports database and file capacity |
| `backup_health` | Evaluates backup recency |
| `checkdb_health` | Reads integrity-check history when available |
| `ag_health` | Reports Availability Group state |
| `job_health` | Reports SQL Agent job failures and state |

### Dashboard-history tools

| Tool | Purpose |
|---|---|
| `list_tracked_instances` | Lists instances represented in collected history |
| `get_severity_trend` | Reads category severity over a requested window |
| `get_latest_snapshot` | Reads the newest collected snapshot for an instance |

## Instance routing

Most live tools accept `instance`. For example, a client can call
`wait_stats(instance="prod")` and then `wait_stats(instance="staging")`
through the same MCP server. When `instance` is omitted, `DEFAULT_INSTANCE` is
used if configured; otherwise the first YAML entry is selected.

The tool response identifies the selected instance but never returns its
connection string.

## Safety model

MCP uses dedicated read-only SQL logins. Ad-hoc SQL is disabled in every
environment. Fixed tools enforce authorization, row/byte limits, timeouts, and
concurrency limits. HTTP requests require verified bearer tokens.

Application policy is defense in depth, not a substitute for SQL Server
permissions. Use a dedicated login that cannot modify schema or data.

## Transports

### HTTP in the unified stack

Compose starts Streamable HTTP at:

```text
http://localhost:8080/mcp
```

Operational endpoints are:

| Endpoint | Meaning |
|---|---|
| `/health` | Process is alive |
| `/ready` | Configuration loaded and configured SQL connections are ready |
| `/info` | Server metadata and enabled capabilities |
| `/metrics` | Prometheus-format metrics when enabled |

An HTTP deployment validates allowed hosts to reduce DNS-rebinding risk. Set
`ALLOWED_HOST` when clients use a hostname other than the local defaults.

### Stdio for local MCP clients

The repository [`.mcp.json`](../.mcp.json) launches `src/mcp` in stdio mode.
For a manual source installation:

```powershell
cd src/mcp
python -m pip install -e .
python -m data_eyes_mcp.cli
```

The process then exchanges MCP JSON-RPC messages over standard input/output.

## Main libraries

| Library | Role |
|---|---|
| `mcp` / FastMCP | Tool registration and MCP transports |
| `pyodbc` | SQL Server connectivity |
| `pydantic-settings` | Typed environment configuration |
| `PyYAML` | Shared fleet loading |
| `FastAPI` and `uvicorn` | HTTP transport and operational endpoints |
| `asyncpg` | Read-only dashboard-history access |
| `prometheus-client` | Metrics |

## Extending MCP

- Add general SQL tools in `src/mcp/src/data_eyes_mcp/tools.py`.
- Add operational diagnostics in `src/mcp/src/data_eyes_mcp/dba_tools.py`.
- Add dashboard-history tools in `src/mcp/src/data_eyes_mcp/repository_tools.py`.
- Put reusable connection and execution behavior in `db.py` rather than
  bypassing policy or limits in individual tools.
- Add tests under `src/mcp/tests/` and update the tool tables above.

See [Development](development.md) for test commands and
[Configuration](configuration.md#mcp-environment) for all runtime controls.
