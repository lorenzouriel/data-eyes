# Availability Group Sync Health

**Script:** `ag_sync_health.sql` · **MCP tool:** `ag_health()`

## Purpose

Per-database AG sync health — a replica can report `HEALTHY` while one of its databases is `NOT SYNCHRONIZING`. Severity-classified.

## Output columns

`DatabaseName`, `Replica`, `SyncState`, `SyncHealth`, `IsPrimaryReplica`, `LogSendQueueKB`, `RedoQueueKB`, `severity`.

## Severity logic

`SyncHealth = NOT_HEALTHY` or `SyncState = NOT SYNCHRONIZING` → `CRITICAL`; queue sizes ≥ 500MB → `CRITICAL`, ≥ 50MB → `WARNING`; `PARTIALLY_HEALTHY` → `WARNING`. Queue thresholds are explicitly heuristic (network/workload dependent) — see `.claude/knowledge-base/_static/thresholds.yaml` (`availability_groups`).

## Notes

Returns an **empty result set, not an error**, on standalone/non-AG instances. Callers should treat that as "no AG", not as healthy or failed.
