# Data Eyes — Diagnostic Taxonomy

Maps every DPA-style category to its script, tool/function name, and where it surfaces in Grafana (panel and/or `alert.<key>` check). This is the routing table the `sql-server-dba` agent, `mcp/`'s tools, and the collector all share — one category system, not three.

**"Tool/function name"** is shared by name, not by call path: the SQL and severity logic live in `mcp/src/data_eyes_mcp/queries.py`. `mcp/src/data_eyes_mcp/tools.py` exposes each query as an MCP tool (live, on demand, for agents). The collector runs its own scheduled alert checks (`monitor/collector/app/alerts/checks/`) and exports their severities to Prometheus as `alert.<key>`.

**Grafana column:** dashboards are *Fleet*, *Instance*, *Database*, and *Health* (`monitor/grafana/dashboards/`). `alert.<key>` checks appear as `data_eyes_health_severity{category="alert.<key>"}` on Fleet → *Category health* and drive the provisioned alert rules; see `docs/features/alerts.md` for units and cadence. "MCP only" means Prometheus holds no equivalent — row-level detail (query text, index definitions, sessions) is never exported as metrics.

| Category | Grafana / alert checks | Script(s) | Tool/function name | Source doc |
|---|---|---|---|---|
| Overview / instance health | Fleet → *Overall health*, *SQL Server reachability*, *Category health* | — (composite) | `fleet_health_score` | `docs/features/metrics.md`, `docs/features/alerts.md` |
| Wait time analysis | Instance → *Wait seconds / second* (by wait category; informational, no alert) | `.claude/resources/performance/additional_queries/wait_statistics.json.sql` | `wait_stats` | `.claude/resources/performance/additional_queries/docs/wait_statistics.md` |
| Missing indexes | MCP only | `.claude/resources/performance/additional_queries/missing_indexes.json.sql` | `missing_indexes` | `.claude/resources/performance/additional_queries/docs/missing_indexes.md` |
| Unused indexes | MCP only | `.claude/resources/performance/additional_queries/unused_indexes.json.sql` | `unused_indexes` | `.claude/resources/performance/additional_queries/docs/unused_indexes.md` |
| Stale statistics | `alert.stale_statistics`; Database → check values/severity | `.claude/resources/performance/additional_queries/update_statistics.json.sql` | `stale_statistics` | `.claude/resources/performance/additional_queries/docs/update_statistics.md` |
| Index fragmentation (live) | `alert.index_fragmentation` (disabled by default) | `.claude/resources/maintenance/diagnostics/fragmentation_live_scan.sql` | `index_fragmentation` | `.claude/resources/maintenance/diagnostics/docs/fragmentation_live_scan.md` |
| Backup health | `alert.full_backup_age`, `alert.log_backup_age`, `alert.backup_failed` | `.claude/resources/maintenance/diagnostics/backup_health_check.sql` | `backup_health` | `.claude/resources/maintenance/diagnostics/docs/backup_health_check.md` |
| CHECKDB / corruption staleness | `alert.checkdb_age`, `alert.database_corruption`, `alert.page_corruption` | `.claude/resources/maintenance/diagnostics/checkdb_staleness.sql` | `checkdb_health` | `.claude/resources/maintenance/diagnostics/docs/checkdb_staleness.md`, `.claude/resources/maintenance/README.md` (CommandLog) |
| Blocking / sessions | Instance → *Blocking duration*; `alert.blocking`, `alert.long_running_process` | `.claude/resources/maintenance/diagnostics/blocking_chain_snapshot.sql` | `blocking_snapshot` | `.claude/resources/maintenance/diagnostics/docs/blocking_chain_snapshot.md` |
| AG / replica sync health | `alert.ag_health`, `alert.ag_data_loss_risk`, `alert.ag_failover` | `.claude/resources/maintenance/diagnostics/ag_sync_health.sql` | `ag_health` | `.claude/resources/maintenance/diagnostics/docs/ag_sync_health.md` |
| SQL Agent job health | `alert.job_failed`, `alert.job_disabled_or_deleted`, `alert.agent_service_stopped` | `.claude/resources/maintenance/diagnostics/job_failure_scan.sql` | `job_health` | `.claude/resources/maintenance/diagnostics/docs/job_failure_scan.md` |
| Top SQL (slow/costly queries) | `alert.slow_queries`, `alert.query_regression` (query text: MCP only) | `.claude/resources/performance/additional_queries/top_queries.json.sql` | `top_queries` | `.claude/resources/performance/additional_queries/docs/top_queries.md` |
| Storage / disk space | Database → *Database size*; `alert.disk_space`, `alert.transaction_log_health`, `alert.maxsize_growth` | `.claude/resources/maintenance/diagnostics/db_space_check.sql` | `db_space` | `.claude/resources/maintenance/diagnostics/docs/db_space_check.md` |

## Trend history (agent-accessible)

The collector exports severity for each `alert.<key>` check plus the instance's `overall` severity to Prometheus (30-day retention). Agents query it via `mcp/`'s `list_tracked_instances`, `get_severity_trend(instance_name, category, hours)` (category `overall` or `alert.<key>`), and `get_latest_snapshot(instance_name)` — a different question ("how has this trended") than the live-SQL tools above answer ("what does this look like right now"). Long ranges use a coarser step and may miss brief transitions. History begins at the first Prometheus scrape.

## Rollup scope

`top_queries` is deliberately excluded from `fleet_health_score`'s rollup (analysis category, not an operational-risk gate); `db_space` is included (disk exhaustion is a real fleet-health signal).

## Health rollup convention

Every diagnostic script/tool in this table returns a `severity` value of `OK`, `WARNING`, or `CRITICAL` per row (see [[thresholds]]). A category's severity is the worst row severity it returns; an instance's severity is the worst category severity; a fleet's severity is the worst instance severity. This "worst-of" rollup is intentionally simple — see `thresholds.yaml`'s header for where to tune it.
