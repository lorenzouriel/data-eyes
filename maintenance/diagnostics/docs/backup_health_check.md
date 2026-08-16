# Backup Health Check

**Script:** `backup_health_check.sql` · **MCP tool:** `backup_health(database=None)`

## Purpose

Answers "is my backup healthy right now" for every user database — a live read, not the copy-paste action scripts in `maintenance/use_cases/`.

## Output columns

| Column | Meaning |
|---|---|
| `DatabaseName`, `RecoveryModel` | — |
| `LastFullBackup`, `FullBackupAgeHours` | Most recent FULL backup and its age |
| `LastDiffBackup` | Most recent DIFF backup (informational, not severity-scored) |
| `LastLogBackup`, `LogBackupAgeMinutes` | Only meaningful when `RecoveryModel <> 'SIMPLE'`; `NULL` for SIMPLE-model databases |
| `severity` | `OK` / `WARNING` / `CRITICAL` |

## Severity logic

Worst of: no FULL backup ever (`CRITICAL`), FULL backup age ≥ 48h (`CRITICAL`) / ≥ 24h (`WARNING`); for non-SIMPLE recovery models, no LOG backup ever (`CRITICAL`), LOG backup age ≥ 240min (`CRITICAL`) / ≥ 60min (`WARNING`). Thresholds match the FULL-daily/LOG-every-30-min cadence in `maintenance/playbook.sql` — see `.claude/knowledge-base/_static/thresholds.yaml`.

## Notes

Reads `msdb.dbo.backupset`, so it reflects backups taken by *any* method (Ola Hallengren, native T-SQL, third-party tools) — not just this toolkit's jobs.
