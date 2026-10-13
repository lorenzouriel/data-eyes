# MCP monitoring server

MCP exposes collector measurements stored in Prometheus. It has no SQL client,
SQL credentials, ODBC drivers, schema tools, or live DMV tools.

## Tools

| Tool | Purpose |
|---|---|
| `list_configured_instances` | Authorized routing metadata; not proof of collection |
| `fleet_overview` | Current reachability, severity, and collection freshness |
| `get_latest_snapshot` | One instance's collected severity |
| `instance_checks` | Check values, severity, units, and database checks |
| `list_databases` | Collected database metadata, state, and size |
| `list_metrics` | Named metric catalog and units |
| `query_metric` | Current measurement; optional counter rate/increase |
| `metric_history` | Last 0.25–720 hours, roughly 121 points per series |
| `get_severity_trend` | Overall or per-check severity history |

`query_metric` and `metric_history` take `instance`, `metric`, `operation`
(`value`, `rate`, `increase`), and optional exact `database`, `category`, `check`
filters. Rate and increase use five-minute windows. No arbitrary PromQL is accepted.
The server constructs selectors with exact authorized instance and environment labels.

Every measurement response includes collection status and last-success timestamps.
`evaluated_at` is Prometheus query time, not SQL collection time. Missing data is
an empty series, not zero. History includes current collection status separately.
Responses are capped at 100 series and 2 MB; queries have a 15-second server timeout,
a 20-second HTTP timeout, and concurrency and per-principal rate limits.

## Configuration and migration

Copy `../mcp-access.example.yaml` to `../mcp-access.yaml`. It contains instance
names, labels, environments, and `mcp_security.principals` (tool/instance grants and
SHA-256 bearer-token hashes). SQL credentials are rejected in its instance entries.
The collector alone reads `instances.yaml`.

For an existing installation, run from the repository root:

```powershell
uv run --project mcp python scripts/migrate_monitoring_access.py
```

This creates a new policy without overwriting an existing one or modifying the source.
Principals that had tools receive the new monitoring catalog, retaining their instance
scope and token hashes. Review grants when a principal previously had a narrow tool role.
New/remapped instances must be updated in both collector inventory and MCP access policy.
An access-policy entry with no current collection is reported as not currently collected.

Set `PROMETHEUS_URL`, `MCP_ACCESS_FILE`, `DEPLOYMENT_ENVIRONMENT`, and optional
`INSTANCE_ALLOWLIST`. Access configuration reloads when its file changes.
HTTP requires bearer authentication. Stdio requires `DEFAULT_PRINCIPAL`.
The existing `.mcp.json` uses loopback Prometheus at port 9090; keep that port local.

```powershell
uv run --project mcp --extra dev pytest mcp/tests -q
```

Manual SQL permission templates for the collector are in `monitor/collector/sql/`.
