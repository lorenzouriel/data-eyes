"""
Maintenance: Agent jobs, index/statistics upkeep, identity limits, new databases, version support.
"""

from datetime import date

from app.alerts.checks.registry import TO_UTC
from app.alerts.checks.registry import check
from app.alerts.checks.registry import for_each_database
from app.alerts.checks.registry import number
from app.alerts.checks.registry import utc
from app.alerts.models import Finding
from app.alerts.models import Occurrence


@check("job_failed")
async def job_failed(ctx):
    last = ctx.memory.get("last_instance_id")
    if last is not None:
        rows = await ctx.query(f"""
        SELECT TOP 100 h.instance_id AS HistoryId, j.name AS JobName,
               {TO_UTC.format("msdb.dbo.agent_datetime(h.run_date, h.run_time)")} AS RunTimeUtc,
               LEFT(h.message, 400) AS Message
        FROM msdb.dbo.sysjobhistory h
        JOIN msdb.dbo.sysjobs j ON j.job_id = h.job_id
        WHERE h.step_id = 0 AND h.run_status = 0 AND h.instance_id > {int(last)}
        ORDER BY h.instance_id
        """)
    else:
        rows = []
    newest = await ctx.query("SELECT ISNULL(MAX(instance_id), 0) AS HistoryId FROM msdb.dbo.sysjobhistory")
    ctx.memory["last_instance_id"] = max([int(last or 0), int(newest[0]["HistoryId"] or 0)] + [row["HistoryId"] for row in rows])
    return [Occurrence(str(row["HistoryId"]), utc(row["RunTimeUtc"], ctx.now), row["JobName"], detail=row["Message"] or "",
                       floor="CRITICAL") for row in rows]


@check("job_disabled_or_deleted")
async def job_disabled_or_deleted(ctx):
    rows = await ctx.query("SELECT CONVERT(varchar(36), job_id) AS JobId, name AS JobName, enabled AS Enabled FROM msdb.dbo.sysjobs")
    current = {row["JobId"]: [row["JobName"], bool(row["Enabled"])] for row in rows}
    previous = ctx.memory.get("jobs")
    ctx.memory["jobs"] = current
    if previous is None:
        return []
    stamp = ctx.now.strftime("%Y%m%d%H%M")
    occurrences = []
    for job_id, (name, enabled) in previous.items():
        if job_id not in current:
            occurrences.append(Occurrence(f"{job_id}:deleted:{stamp}", ctx.now, name, detail="job deleted", floor="WARNING"))
        elif enabled and not current[job_id][1]:
            occurrences.append(Occurrence(f"{job_id}:disabled:{stamp}", ctx.now, name, detail="job disabled", floor="WARNING"))
    return occurrences


@check("rebuild_failed")
async def rebuild_failed(ctx):
    last = ctx.memory.get("last_id")
    # CommandLog is optional, so it is only referenced through dynamic SQL.
    failures = "" if last is None else f"""
        INSERT INTO #f (ID, DatabaseName, ObjectName, IndexName, CommandType, EndTimeUtc, ErrorNumber)
        EXEC sys.sp_executesql N'
            SELECT TOP 100 ID, DatabaseName, ObjectName, IndexName, CommandType, {TO_UTC.format("EndTime")}, ErrorNumber
            FROM master.dbo.CommandLog
            WHERE CommandType IN (N''ALTER_INDEX'', N''UPDATE_STATISTICS'') AND ErrorNumber <> 0 AND ID > @last
            ORDER BY ID', N'@last int', @last = {int(last)};"""
    rows = await ctx.query(f"""
    SET NOCOUNT ON;
    CREATE TABLE #f (ID int NULL, DatabaseName sysname NULL, ObjectName sysname NULL, IndexName sysname NULL,
                     CommandType nvarchar(60) NULL, EndTimeUtc datetime NULL, ErrorNumber int NULL, MaxId int NULL);
    IF OBJECT_ID(N'master.dbo.CommandLog') IS NOT NULL
    BEGIN
        {failures}
        INSERT INTO #f (MaxId) EXEC sys.sp_executesql N'SELECT MAX(ID) FROM master.dbo.CommandLog';
    END;
    SELECT ID, DatabaseName, ObjectName, IndexName, CommandType, EndTimeUtc, ErrorNumber, MaxId FROM #f;
    """)
    ids = [int(row["MaxId"]) for row in rows if row["MaxId"] is not None]
    ctx.memory["last_id"] = max(ids + [int(last or 0)])
    return [Occurrence(str(row["ID"]), utc(row["EndTimeUtc"], ctx.now),
                       f"{row['DatabaseName']} {row['ObjectName']}" + (f".{row['IndexName']}" if row["IndexName"] else ""),
                       database=row["DatabaseName"], detail=f"{row['CommandType']} failed with error {row['ErrorNumber']}",
                       floor="WARNING")
            for row in rows if row["ID"] is not None]


@check("index_fragmentation")
async def index_fragmentation(ctx):
    rows = await ctx.query("""
    SELECT TOP 50 DB_NAME(ps.database_id) AS DatabaseName, OBJECT_NAME(ps.object_id, ps.database_id) AS ObjectName,
           ps.index_id AS IndexId, ps.avg_fragmentation_in_percent AS FragmentationPct, ps.page_count AS PageCount
    FROM sys.dm_db_index_physical_stats(NULL, NULL, NULL, NULL, 'LIMITED') ps
    WHERE ps.page_count > 1000 AND ps.index_id > 0 AND ps.avg_fragmentation_in_percent >= 10
    ORDER BY ps.avg_fragmentation_in_percent DESC
    """)
    return [Finding(f"{row['DatabaseName']} {row['ObjectName']} index {row['IndexId']}", round(number(row["FragmentationPct"]) or 0, 1),
                    database=row["DatabaseName"], detail=f"{row['PageCount']:,} pages") for row in rows]


@check("stale_statistics")
async def stale_statistics(ctx):
    rows = await ctx.query(for_each_database(
        "SELECT TOP 20 DB_NAME(), OBJECT_SCHEMA_NAME(s.object_id) + N'.' + OBJECT_NAME(s.object_id), s.name, "
        "DATEDIFF(DAY, sp.last_updated, GETDATE()), sp.modification_counter "
        "FROM sys.stats s CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp "
        "WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1 AND sp.modification_counter >= 1000 "
        "ORDER BY sp.last_updated ASC",
        "DatabaseName sysname, TableName nvarchar(300), StatName sysname, DaysOld int, Modifications bigint",
        where="database_id > 4 AND is_read_only = 0",
    ))
    return [Finding(f"{row['DatabaseName']} {row['TableName']}.{row['StatName']}", number(row["DaysOld"]),
                    database=row["DatabaseName"], detail=f"{row['Modifications']:,} modifications since last update") for row in rows]


@check("identity_values")
async def identity_values(ctx):
    rows = await ctx.query(for_each_database(
        "SELECT DB_NAME(), OBJECT_SCHEMA_NAME(ic.object_id) + N'.' + OBJECT_NAME(ic.object_id), ic.name, t.name, "
        "CAST(ic.last_value AS decimal(38, 0)), "
        "CAST(100.0 * CAST(ic.last_value AS decimal(38, 0)) / CASE t.name WHEN N'tinyint' THEN 255 WHEN N'smallint' THEN 32767 "
        "WHEN N'int' THEN 2147483647 ELSE 9223372036854775807 END AS decimal(9, 4)) "
        "FROM sys.identity_columns ic JOIN sys.types t ON t.user_type_id = ic.system_type_id "
        "WHERE t.name IN (N'tinyint', N'smallint', N'int', N'bigint') AND ic.last_value IS NOT NULL "
        "AND CAST(ic.increment_value AS bigint) > 0 AND OBJECTPROPERTY(ic.object_id, 'IsUserTable') = 1 "
        # Only columns past a quarter of their range are returned.
        "AND CAST(ic.last_value AS decimal(38, 0)) >= CASE t.name WHEN N'tinyint' THEN 63 WHEN N'smallint' THEN 8191 "
        "WHEN N'int' THEN 536870911 ELSE 2305843009213693951 END",
        "DatabaseName sysname, TableName nvarchar(300), ColumnName sysname, TypeName sysname, "
        "LastValue decimal(38, 0), PctUsed decimal(9, 4)",
    ))
    return [Finding(f"{row['DatabaseName']} {row['TableName']}.{row['ColumnName']}", round(number(row["PctUsed"]) or 0, 2),
                    database=row["DatabaseName"], detail=f"{row['TypeName']} at {row['LastValue']:,}") for row in rows]


@check("new_database")
async def new_database(ctx):
    rows = await ctx.query(f"""
    SELECT d.name AS DatabaseName, CONVERT(varchar(23), d.create_date, 121) AS CreateDate,
           {TO_UTC.format("d.create_date")} AS CreateDateUtc,
           CASE WHEN EXISTS (SELECT 1 FROM msdb.dbo.backupset b
                             WHERE b.database_name = d.name AND b.[type] = 'D' AND b.backup_finish_date >= d.create_date)
                THEN 1 ELSE 0 END AS HasFullBackup
    FROM sys.databases d
    WHERE d.database_id > 4 AND d.source_database_id IS NULL
    """)
    current = {row["DatabaseName"]: row["CreateDate"] for row in rows}
    previous = ctx.memory.get("databases")
    ctx.memory["databases"] = current
    if previous is None:
        return []
    return [Occurrence(f"{row['DatabaseName']}:{row['CreateDate']}", utc(row["CreateDateUtc"], ctx.now), row["DatabaseName"],
                       database=row["DatabaseName"], floor="WARNING",
                       detail=f"created {row['CreateDate']} (server time); "
                              + ("has a full backup" if row["HasFullBackup"] else "no full backup yet — add it to backup and maintenance jobs"))
            for row in rows if previous.get(row["DatabaseName"]) != row["CreateDate"]]


# Microsoft extended-support end dates by major version.
END_OF_SUPPORT = {
    10: date(2019, 7, 9), 11: date(2022, 7, 12), 12: date(2024, 7, 9), 13: date(2026, 7, 14),
    14: date(2027, 10, 12), 15: date(2030, 1, 8), 16: date(2033, 1, 11),
}
_NAMES = {10: "2008/2008 R2", 11: "2012", 12: "2014", 13: "2016", 14: "2017", 15: "2019", 16: "2022"}


@check("version_support")
async def version_support(ctx):
    rows = await ctx.query("""
    SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(64)) AS ProductVersion,
           CAST(SERVERPROPERTY('ProductLevel') AS nvarchar(64)) AS ProductLevel,
           CAST(SERVERPROPERTY('ProductUpdateLevel') AS nvarchar(64)) AS UpdateLevel,
           CAST(SERVERPROPERTY('EngineEdition') AS int) AS EngineEdition
    """)
    if not rows or rows[0]["EngineEdition"] in (5, 8):  # Azure SQL Database / Managed Instance are evergreen
        return []
    row = rows[0]
    major = int(str(row["ProductVersion"]).split(".")[0])
    end = END_OF_SUPPORT.get(major)
    label = f"SQL Server {_NAMES.get(major, major)} {row['ProductVersion']} {row['ProductLevel']} {row['UpdateLevel'] or ''}".strip()
    if end is None:
        return [Finding(label, detail="lifecycle date unknown; newer than this check" if major > 16 else "out of support",
                        floor=None if major > 16 else "CRITICAL")]
    return [Finding(label, float((end - ctx.now.date()).days), detail=f"extended support ends {end.isoformat()}")]
