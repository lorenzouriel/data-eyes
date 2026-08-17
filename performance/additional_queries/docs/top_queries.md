# Top Queries by Average Duration

**Script:** `top_queries.json.sql` · **MCP tool:** `top_queries(database=None, top_n=25)`

## Purpose

Ranks queries by average elapsed time per execution — the "Top SQL" DPA-style tab. Ports and merges the "Top 10 Longest Running Queries" (`monitor/docs/query_perfomance.md`) and "Slow Query Alerts (> 30s)" (`monitor/docs/other_metrics.md`) panels, which previously existed only as inline Grafana panel SQL with no standalone script.

## Output columns

`DatabaseName`, `ExecutionCount`, `AvgElapsedTimeMs`, `AvgCpuTimeMs`, `AvgLogicalReads`, `MaxElapsedTimeMs`, `LastExecutionTime`, `QueryText`, `severity`.

## Severity logic

`AvgElapsedTimeMs ≥ 30000` (30s) → `CRITICAL` — deliberately matches the threshold `other_metrics.md` already used for its "Slow Query Alerts" panel, not a new number. `≥ 5000` (5s) → `WARNING` (heuristic — no other doc value exists for a warning tier). See `.claude/knowledge-base/_static/thresholds.yaml` (`query_performance.avg_duration_ms`).

## Notes

Reads `sys.dm_exec_query_stats`, which is plan-cache-scoped — like the missing/unused index DMVs, this resets on service restart and only reflects queries whose plan is still cached. Not a substitute for Query Store history on SQL Server 2016+, which retains data across restarts and plan-cache eviction (see `performance/README.md` Step 0 for enabling it).
