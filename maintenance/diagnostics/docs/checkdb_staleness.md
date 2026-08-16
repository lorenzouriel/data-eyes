# CHECKDB Staleness + Suspect Pages

**Script:** `checkdb_staleness.sql` · **MCP tool:** `checkdb_health(database=None)`

## Purpose

Answers "is there corruption, and when did we last check" — before this script, `maintenance/` had zero live corruption-related reads.

## Output columns

| Column | Meaning |
|---|---|
| `DatabaseName` | — |
| `LastCheckDBEndTime`, `DaysSinceLastCheckDB` | From `master.dbo.CommandLog`, `CommandType LIKE '%CHECK%'` |
| `SuspectPageCount` | From `msdb.dbo.suspect_pages`, active (uncleaned) entries only |
| `severity` | `OK` / `WARNING` / `CRITICAL` |

## Severity logic

Any suspect pages → `CRITICAL` regardless of staleness. Otherwise: never checked → `CRITICAL`; ≥14 days stale → `CRITICAL`; ≥7 days stale → `WARNING`. See `.claude/knowledge-base/_static/thresholds.yaml` (`maintenance.checkdb`).

## Prerequisite

`master.dbo.CommandLog` only exists once Ola Hallengren's maintenance scripts are installed (see `maintenance/README.md`). A database that has never run CHECKDB through that path reports `LastCheckDBEndTime = NULL` and `severity = CRITICAL` — not a false positive, a real gap.
