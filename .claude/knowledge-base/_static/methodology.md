# Data Eyes — Performance Tuning Methodology (canonical)

**Canonical name: the 10-step methodology, Steps 0–9.** `.claude/resources/performance/README.md` and `CLAUDE.md` both now say "10-step," matching this file's step count.

**Core principle:** one change at a time, measure before and after.

| Step | Objective | Script | Key thresholds ([[thresholds]]) |
|---|---|---|---|
| 0 – Prep | Document environment, enable Query Store | — | — |
| 1 – Baseline | Capture current state before changing anything | `wait_statistics.sql` / `wait_stats` tool | — |
| 2 – Workload Analysis | Find and fix the worst queries and indexes | `missing_indexes.sql`, `unused_indexes.sql`, `update_statistics.sql` (+ `.json.sql`/tool equivalents) | `index.fragmentation_pct`, `index.stats_staleness_days` |
| 3 – Contention | Eliminate blocking and deadlocks | `.claude/resources/maintenance/diagnostics/blocking_chain_snapshot.sql` / `blocking_snapshot` tool | `waits.blocking_duration_seconds` |
| 4 – TempDB | Optimize TempDB for concurrency | — (watch `PAGELATCH_UP`/`PAGELATCH_EX` in wait stats) | — |
| 5 – Memory | Ensure adequate memory, detect pressure | — (PerfMon / DMV) | `memory.page_life_expectancy_seconds`, `memory.buffer_cache_hit_pct`, `memory.memory_grants_pending` |
| 6 – CPU | Optimize CPU utilization and parallelism | — | `cpu.sustained_pct` |
| 7 – I/O / Log | Optimize disk I/O and log performance | — | `io.data_file_latency_ms`, `io.log_file_latency_ms` |
| 8 – Config Review | Validate configuration vs. best practices | — | — |
| 9 – Verify | Re-measure, compare before/after | rerun Step 1 scripts | — |

Full step-by-step actions/guidance remain in `.claude/resources/performance/README.md` — this file is the compact, agent/tool-facing index, not a replacement for that narrative doc.

**Maintenance methodology (parallel track, not part of the 10 steps above):** backup/CHECKDB/index-rebuild automation lives in `.claude/resources/maintenance/` (Ola Hallengren-based, see `.claude/resources/maintenance/README.md`), and the new live-observation diagnostics (`backup_health`, `checkdb_health`, `ag_health`, `job_health`) close the gap where the maintenance track previously had zero "is it healthy right now" queries — see `[[scripts-index]]`.
