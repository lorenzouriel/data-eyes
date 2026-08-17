# Database Space & Drive Free Space

**Script:** `db_space_check.sql` · **MCP tool:** `db_space(database=None)`

## Purpose

Per-file size/free-space plus the underlying drive's free space — the "Storage" DPA-style tab. Ports `monitor/docs/database_space_usage.md`'s "Database size per database" panel, which previously existed only as inline Grafana panel SQL.

## Output columns

`DatabaseName`, `FileName`, `FileType` (`ROWS`/`LOG`), `FileSizeMB`, `FreeSpaceMB`, `FreeSpacePct`, `DriveSizeGB`, `DriveFreeSpaceGB`, `severity`.

## Severity logic

Driven by **drive** free space, not file free space — a database can have generous free space inside its own files while the disk hosting it is nearly full, which is the actual outage risk (autogrowth failure, transaction log full). `DriveFreeSpaceGB < 5` → `CRITICAL`; `< 20` → `WARNING`. Both are explicitly heuristic (a 100GB local disk and a multi-TB SAN LUN need very different alarms) — see `.claude/knowledge-base/_static/thresholds.yaml` (`storage.drive_free_space_gb`), tune per host.

## Notes

Uses `sys.dm_os_volume_stats`, which requires the connected login to be able to read volume mount info — on some locked-down hosts this can return `NULL` drive figures; `FreeSpacePct` (file-internal, always available) still works standalone in that case.
