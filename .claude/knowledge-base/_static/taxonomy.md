# Data Eyes — Diagnostic Taxonomy

Maps every DPA-style category to its script, tool/function name, and its dashboard tab. This is the routing table the `sql-server-dba` agent, `mcp/`'s tools, and the dashboard backend all share — one category system, not three.

**"Tool/function name"** is shared by name, not by call path: `mcp/src/data_eyes_mcp/dba_tools.py` exposes it as an `@mcp.tool()` (for Claude Code), and `dashboard/backend/app/diagnostics.py` exposes the identical query + severity logic as a plain async function of the same name (for the dashboard's own direct-SQL rendering path — no MCP hop). Same SQL, same thresholds, two callers.

| Category | Tab | Script(s) | Tool/function name | Source doc |
|---|---|---|---|---|
| Overview / instance health | Overview | — (composite) | `fleet_health_score` | `monitor/docs/general.md`, `monitor/docs/availability_groups.md` |
| Wait time analysis | Wait Time Analysis | `.claude/resources/performance/additional_queries/wait_statistics.json.sql` | `wait_stats` | `.claude/resources/performance/additional_queries/docs/wait_statistics.md` |
| Missing indexes | Index & Buffer | `.claude/resources/performance/additional_queries/missing_indexes.json.sql` | `missing_indexes` | `.claude/resources/performance/additional_queries/docs/missing_indexes.md` |
| Unused indexes | Index & Buffer | `.claude/resources/performance/additional_queries/unused_indexes.json.sql` | `unused_indexes` | `.claude/resources/performance/additional_queries/docs/unused_indexes.md` |
| Stale statistics | Index & Buffer | `.claude/resources/performance/additional_queries/update_statistics.json.sql` | `stale_statistics` | `.claude/resources/performance/additional_queries/docs/update_statistics.md` |
| Index fragmentation (live) | Index & Buffer | `.claude/resources/maintenance/diagnostics/fragmentation_live_scan.sql` | `index_fragmentation` | `.claude/resources/maintenance/diagnostics/docs/fragmentation_live_scan.md` |
| Backup health | Configuration / Alerts | `.claude/resources/maintenance/diagnostics/backup_health_check.sql` | `backup_health` | `.claude/resources/maintenance/diagnostics/docs/backup_health_check.md`, `monitor/docs/other_metrics.md` |
| CHECKDB / corruption staleness | Configuration / Alerts | `.claude/resources/maintenance/diagnostics/checkdb_staleness.sql` | `checkdb_health` | `.claude/resources/maintenance/diagnostics/docs/checkdb_staleness.md`, `.claude/resources/maintenance/README.md` (CommandLog) |
| Blocking / sessions | Sessions / Blocking | `.claude/resources/maintenance/diagnostics/blocking_chain_snapshot.sql` | `blocking_snapshot` | `.claude/resources/maintenance/diagnostics/docs/blocking_chain_snapshot.md`, `monitor/docs/database_space_usage.md` (Active Locks) |
| AG / replica sync health | AG (conditional tab) | `.claude/resources/maintenance/diagnostics/ag_sync_health.sql` | `ag_health` | `monitor/docs/availability_groups.md` |
| SQL Agent job health | Configuration / Alerts | `.claude/resources/maintenance/diagnostics/job_failure_scan.sql` | `job_health` | `monitor/docs/jobs_monitoring.md` |
| Top SQL (slow/costly queries) | Top SQL | `.claude/resources/performance/additional_queries/top_queries.json.sql` | `top_queries` | `.claude/resources/performance/additional_queries/docs/top_queries.md`, `monitor/docs/query_perfomance.md`, `monitor/docs/other_metrics.md` |
| Storage / disk space | Storage | `.claude/resources/maintenance/diagnostics/db_space_check.sql` | `db_space` | `.claude/resources/maintenance/diagnostics/docs/db_space_check.md`, `monitor/docs/database_space_usage.md` |

## Trend history (agent-accessible)

Historical severity/metric data for these categories, as collected by the dashboard's background collector, is queryable by an agent via `mcp/`'s `get_severity_trend(instance_name, category, hours)` and `get_latest_snapshot(instance_name)` — a different question ("how has this trended") than the live-SQL tools above answer ("what does this look like right now"). See `mcp/README.md`'s "Dashboard Repository Trend Tools" section.

## Closed gaps

Top SQL and Storage previously existed only as inline Grafana panel SQL in `monitor/dashboards/sqlserver.json` with no standalone script or MCP tool — closed in the Phase 3 (per-database drill-down) pass. `top_queries` is deliberately excluded from `fleet_health_score`'s rollup (analysis category, not an operational-risk gate); `db_space` is included (disk exhaustion is a real fleet-health signal).

## Health rollup convention

Every diagnostic script/tool in this table returns a `severity` value of `OK`, `WARNING`, or `CRITICAL` per row (see [[thresholds]]). A category's severity is the worst row severity it returns; an instance's severity is the worst category severity; a fleet's severity is the worst instance severity. This "worst-of" rollup is intentionally simple — see `thresholds.yaml`'s header for where to tune it.
