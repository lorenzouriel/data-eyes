# Availability Group Sync Health

**Script:** `ag_sync_health.sql` · **MCP tool:** `ag_health()`

## Purpose

Per-database AG sync health — a replica can report `HEALTHY` while one of its databases is `NOT SYNCHRONIZING`. Ports the query already documented in `monitor/docs/availability_groups.md` into a severity-classified form.

## Output columns

`DatabaseName`, `Replica`, `SyncState`, `SyncHealth`, `IsPrimaryReplica`, `LogSendQueueKB`, `RedoQueueKB`, `severity`.

## Severity logic

`SyncHealth = NOT_HEALTHY` or `SyncState = NOT SYNCHRONIZING` → `CRITICAL`; queue sizes ≥ 500MB → `CRITICAL`, ≥ 50MB → `WARNING`; `PARTIALLY_HEALTHY` → `WARNING`. Queue thresholds are explicitly heuristic (network/workload dependent) — see `.claude/knowledge-base/_static/thresholds.yaml` (`availability_groups`).

## Notes

Returns an **empty result set, not an error**, on standalone/non-AG instances. The dashboard's AG tab (per the rearchitecture plan) should hide itself when this returns nothing, matching how `fleet_overview.json`'s `STANDALONE` handling already works.
