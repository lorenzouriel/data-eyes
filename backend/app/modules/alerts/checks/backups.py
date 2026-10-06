"""Backup and integrity: backup age, failed backups, CHECKDB, corruption."""

import re

from app.modules.alerts.checks.registry import check
from app.modules.alerts.checks.registry import digest
from app.modules.alerts.checks.registry import number
from app.modules.alerts.checks.registry import read_error_log
from app.modules.alerts.checks.registry import utc
from app.modules.alerts.models import Finding
from app.modules.alerts.models import Occurrence

NEW_DATABASE_DAYS = 7

# Backups taken on a non-preferred AG replica are expected to be missing here.
_BACKUP_SCOPE = """
    d.state_desc = N'ONLINE' AND d.source_database_id IS NULL
    AND (d.replica_id IS NULL OR sys.fn_hadr_backup_is_preferred_replica(d.name) = 1)
"""


@check("full_backup_age")
async def full_backup_age(ctx):
    rows = await ctx.query(f"""
    WITH LastFull AS (
        SELECT database_name, MAX(backup_finish_date) AS LastFullBackup
        FROM msdb.dbo.backupset
        WHERE [type] = 'D'
        GROUP BY database_name
    )
    SELECT d.name AS DatabaseName,
           CONVERT(varchar(16), lf.LastFullBackup, 120) AS LastFullBackup,
           DATEDIFF(HOUR, COALESCE(lf.LastFullBackup, d.create_date), GETDATE()) AS AgeHours,
           DATEDIFF(DAY, d.create_date, GETDATE()) AS AgeOfDatabaseDays
    FROM sys.databases d
    LEFT JOIN LastFull lf ON lf.database_name = d.name
    WHERE d.database_id <> 2 AND {_BACKUP_SCOPE}
    """)
    return [_since_or_never(row, row["LastFullBackup"], "AgeHours", f"last full {row['LastFullBackup']}", "never backed up")
            for row in rows]


def _since_or_never(row, last, age_column, seen, never):
    """A database never backed up or checked is measured from its creation
    only while it is new (a grace period). After that it is simply critical:
    system databases report a 2003 template creation date, so an age would be
    a meaningless number."""
    if last or (number(row["AgeOfDatabaseDays"]) or 0) < NEW_DATABASE_DAYS:
        return Finding(row["DatabaseName"], number(row[age_column]), database=row["DatabaseName"], detail=seen if last else never)
    return Finding(row["DatabaseName"], database=row["DatabaseName"], detail=never, floor="CRITICAL")


@check("log_backup_age")
async def log_backup_age(ctx):
    rows = await ctx.query(f"""
    WITH LastBackups AS (
        SELECT database_name,
               MAX(CASE WHEN [type] = 'D' THEN backup_finish_date END) AS LastFull,
               MAX(CASE WHEN [type] = 'L' THEN backup_finish_date END) AS LastLog
        FROM msdb.dbo.backupset
        GROUP BY database_name
    )
    SELECT d.name AS DatabaseName, d.recovery_model_desc AS RecoveryModel,
           CONVERT(varchar(16), lb.LastLog, 120) AS LastLogBackup,
           DATEDIFF(MINUTE, COALESCE(lb.LastLog, lb.LastFull), GETDATE()) AS AgeMinutes
    FROM sys.databases d
    JOIN LastBackups lb ON lb.database_name = d.name AND lb.LastFull IS NOT NULL
    WHERE d.database_id > 4 AND d.recovery_model_desc <> N'SIMPLE' AND d.is_read_only = 0 AND {_BACKUP_SCOPE}
    """)
    return [Finding(row["DatabaseName"], number(row["AgeMinutes"]), database=row["DatabaseName"],
                    detail=f"{row['RecoveryModel']}; last log {row['LastLogBackup'] or 'never'}") for row in rows]


_BACKUP_FAILED = re.compile(r"BACKUP failed to complete the command (BACKUP (?:DATABASE|LOG)) (\S+?)\.?(?:\s|$)")


@check("backup_failed")
async def backup_failed(ctx):
    rows = await read_error_log(ctx, "BACKUP failed to complete")
    occurrences = []
    for row in rows or []:
        match = _BACKUP_FAILED.search(row["Text"])
        database = match.group(2).strip("[]") if match else None
        occurrences.append(Occurrence(digest(row["LogDate"], row["ProcessInfo"], row["Text"]), utc(row["LogDateUtc"], ctx.now),
                                      database or "Backup", database=database,
                                      detail=f"{match.group(1) if match else 'BACKUP'} failed at {row['LogDate']} (server time)",
                                      floor="CRITICAL"))
    return occurrences


@check("checkdb_age")
async def checkdb_age(ctx):
    rows = await ctx.query("""
    SELECT d.name AS DatabaseName,
           CONVERT(varchar(16), lg.LastGood, 120) AS LastGoodCheckDb,
           DATEDIFF(DAY, COALESCE(lg.LastGood, d.create_date), GETDATE()) AS AgeDays,
           DATEDIFF(DAY, d.create_date, GETDATE()) AS AgeOfDatabaseDays
    FROM sys.databases d
    CROSS APPLY (SELECT NULLIF(CAST(DATABASEPROPERTYEX(d.name, 'LastGoodCheckDbTime') AS datetime), '19000101') AS LastGood) lg
    WHERE d.database_id <> 2 AND d.state_desc = N'ONLINE' AND d.source_database_id IS NULL
    """)
    return [_since_or_never(row, row["LastGoodCheckDb"], "AgeDays", f"last clean CHECKDB {row['LastGoodCheckDb']}",
                            "no clean CHECKDB recorded") for row in rows]


@check("database_corruption")
async def database_corruption(ctx):
    rows = await ctx.query("""
    SET NOCOUNT ON;
    CREATE TABLE #c (DatabaseName sysname NULL, EndTime varchar(16) NULL, ErrorNumber int NULL);
    IF OBJECT_ID(N'master.dbo.CommandLog') IS NOT NULL
        INSERT INTO #c EXEC sys.sp_executesql N'
            WITH LastRun AS (
                SELECT DatabaseName, EndTime, ErrorNumber,
                       ROW_NUMBER() OVER (PARTITION BY DatabaseName ORDER BY StartTime DESC) AS rn
                FROM master.dbo.CommandLog
                WHERE CommandType = N''DBCC_CHECKDB''
            )
            SELECT DatabaseName, CONVERT(varchar(16), EndTime, 120), ErrorNumber
            FROM LastRun WHERE rn = 1 AND ErrorNumber <> 0';
    SELECT DatabaseName, EndTime, ErrorNumber FROM #c;
    """)
    return [Finding(row["DatabaseName"], database=row["DatabaseName"], floor="CRITICAL",
                    detail=f"latest CHECKDB ({row['EndTime'] or 'still running'}) ended with error {row['ErrorNumber']}")
            for row in rows]


@check("page_corruption")
async def page_corruption(ctx):
    rows = await ctx.query("""
    SELECT DB_NAME(database_id) AS DatabaseName, COUNT(*) AS SuspectPages,
           CONVERT(varchar(16), MAX(last_update_date), 120) AS LastSeen
    FROM msdb.dbo.suspect_pages
    WHERE event_type IN (1, 2, 3)
    GROUP BY database_id
    """)
    return [Finding(row["DatabaseName"] or "Unknown database", number(row["SuspectPages"]), database=row["DatabaseName"],
                    detail=f"last seen {row['LastSeen']}") for row in rows]


_ERROR_HEADER = re.compile(r"Error: (\d+), Severity: (\d+), State: (\d+)")
_IO_MEANING = {823: "operating system I/O error", 824: "logical consistency I/O error (checksum or torn page)",
               825: "read succeeded only after retrying"}


def parse_error_header(text):
    match = _ERROR_HEADER.search(text or "")
    return tuple(int(part) for part in match.groups()) if match else None


@check("io_corruption_errors")
async def io_corruption_errors(ctx):
    rows = await read_error_log(ctx, "Error: 82")
    occurrences = []
    for row in rows or []:
        header = parse_error_header(row["Text"])
        if not header or header[0] not in _IO_MEANING:
            continue
        error, severity, state = header
        occurrences.append(Occurrence(digest(row["LogDate"], row["ProcessInfo"], row["Text"]), utc(row["LogDateUtc"], ctx.now),
                                      f"Error {error}", detail=f"{_IO_MEANING[error]}; severity {severity}, state {state}, "
                                      f"{row['ProcessInfo']} at {row['LogDate']} (server time). Run DBCC CHECKDB and check storage.",
                                      floor="WARNING" if error == 825 else "CRITICAL"))
    return occurrences
