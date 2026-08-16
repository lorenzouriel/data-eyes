# Data Eyes — Diagnostic Taxonomy

Maps every DPA-style category to its script, MCP tool, and (for the future dashboard) its tab. This is the routing table the `sql-server-dba` agent, the MCP server, and the dashboard backend all share — one category system, not three.

| Category | Tab (future dashboard) | Script(s) | MCP tool | Source doc |
|---|---|---|---|---|
| Overview / instance health | Overview | — (composite) | `fleet_health_score` | `monitor/docs/general.md`, `monitor/docs/availability_groups.md` |
| Wait time analysis | Wait Time Analysis | `performance/additional_queries/wait_statistics.json.sql` | `wait_stats` | `performance/additional_queries/docs/wait_statistics.md` |
| Missing indexes | Index & Buffer | `performance/additional_queries/missing_indexes.json.sql` | `missing_indexes` | `performance/additional_queries/docs/missing_indexes.md` |
| Unused indexes | Index & Buffer | `performance/additional_queries/unused_indexes.json.sql` | `unused_indexes` | `performance/additional_queries/docs/unused_indexes.md` |
| Stale statistics | Index & Buffer | `performance/additional_queries/update_statistics.json.sql` | `stale_statistics` | `performance/additional_queries/docs/update_statistics.md` |
| Index fragmentation (live) | Index & Buffer | `maintenance/diagnostics/fragmentation_live_scan.sql` | `index_fragmentation` | `maintenance/diagnostics/docs/fragmentation_live_scan.md` |
| Backup health | Configuration / Alerts | `maintenance/diagnostics/backup_health_check.sql` | `backup_health` | `maintenance/diagnostics/docs/backup_health_check.md`, `monitor/docs/other_metrics.md` |
| CHECKDB / corruption staleness | Configuration / Alerts | `maintenance/diagnostics/checkdb_staleness.sql` | `checkdb_health` | `maintenance/diagnostics/docs/checkdb_staleness.md`, `maintenance/README.md` (CommandLog) |
| Blocking / sessions | Sessions / Blocking | `maintenance/diagnostics/blocking_chain_snapshot.sql` | `blocking_snapshot` | `maintenance/diagnostics/docs/blocking_chain_snapshot.md`, `monitor/docs/database_space_usage.md` (Active Locks) |
| AG / replica sync health | AG (conditional tab) | `maintenance/diagnostics/ag_sync_health.sql` | `ag_health` | `monitor/docs/availability_groups.md` |
| SQL Agent job health | Configuration / Alerts | `maintenance/diagnostics/job_failure_scan.sql` | `job_health` | `monitor/docs/jobs_monitoring.md` |
| Top SQL (slow/costly queries) | Top SQL | *not yet extracted — see gap below* | *pending* | `monitor/docs/query_perfomance.md`, `monitor/docs/other_metrics.md` |
| Storage / disk space | Storage / Disk Space | *not yet extracted — see gap below* | *pending* | `monitor/docs/database_space_usage.md` |

## Known gaps (tracked, not yet closed)

Two categories exist today only as inline Grafana panel SQL in `monitor/dashboards/sqlserver.json` and prose in `monitor/docs/`, with no standalone script or MCP tool yet:

- **Top SQL** — top CPU/duration/logical-reads queries (`monitor/docs/query_perfomance.md`, `monitor/docs/other_metrics.md`). Needs a `performance/additional_queries/top_queries.json.sql` + a `top_queries` MCP tool.
- **Storage / disk space** — per-database/file size, free space, drive space (`monitor/docs/database_space_usage.md`). Needs a `maintenance/diagnostics/db_space_check.sql` + a `db_space` MCP tool.

These are scoped for the dashboard-app phase (when the "Top SQL" and "Storage" tabs are actually built), not part of this knowledge-base/MCP foundation pass.

## Health rollup convention

Every diagnostic script/tool in this table returns a `severity` value of `OK`, `WARNING`, or `CRITICAL` per row (see [[thresholds]]). A category's severity is the worst row severity it returns; an instance's severity is the worst category severity; a fleet's severity is the worst instance severity. This "worst-of" rollup is intentionally simple — see `thresholds.yaml`'s header for where to tune it.
