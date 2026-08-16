# SQL Agent Job Health

**Script:** `job_failure_scan.sql` · **MCP tool:** `job_health()`

## Purpose

Most recent run outcome and 7-day failure count per enabled job — ports `monitor/docs/jobs_monitoring.md`'s "Failed Job Runs" and "Job Run History" queries into one severity-classified form.

## Output columns

`JobName`, `LastRunDateTime`, `LastRunStatus` (`Succeeded`/`Failed`/`Retry`/`Canceled`/`Unknown`), `LastRunMessage`, `FailuresLast7Days`, `severity`.

## Severity logic

Most recent run failed → `CRITICAL`; most recent run succeeded but ≥1 failure in the last 7 days → `WARNING`; otherwise `OK`. Lookback window is configurable in `.claude/knowledge-base/_static/thresholds.yaml` (`maintenance.jobs.failure_lookback_days`).

## Notes

Jobs are instance-level, not per-database — unlike the other `diagnostics/` scripts, this one has no `@DatabaseName` parameter. Disabled jobs are excluded entirely (not scored).
