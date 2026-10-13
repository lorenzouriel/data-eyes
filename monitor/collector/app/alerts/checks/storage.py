"""
Storage and tempdb: disk, logs, file growth, VLFs, I/O latency, tempdb.
"""

from datetime import datetime

from app.alerts.checks.registry import TO_UTC
from app.alerts.checks.registry import check
from app.alerts.checks.registry import digest
from app.alerts.checks.registry import number
from app.alerts.checks.registry import server_now
from app.alerts.checks.registry import as_datetime
from app.alerts.checks.registry import utc
from app.alerts.models import Finding
from app.alerts.models import Occurrence

_LOG_USED_COUNTER = """
    pc.object_name LIKE N'%:Databases%' AND pc.counter_name = N'Percent Log Used'
"""
_MIN_SCORED_LOG_MB = 64


@check("disk_space")
async def disk_space(ctx):
    rows = await ctx.query("""
    SELECT DISTINCT vs.volume_mount_point AS Drive,
           CAST(vs.total_bytes / 1073741824.0 AS decimal(18, 2)) AS DriveSizeGB,
           CAST(vs.available_bytes / 1073741824.0 AS decimal(18, 2)) AS FreeGB,
           CAST(100.0 * vs.available_bytes / NULLIF(vs.total_bytes, 0) AS decimal(5, 2)) AS FreePct
    FROM sys.master_files mf
    JOIN sys.databases d ON d.database_id = mf.database_id AND d.state_desc = N'ONLINE'
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    """)
    return [Finding(row["Drive"], number(row["FreeGB"]), detail=f"{row['FreePct']}% of {row['DriveSizeGB']} GB free")
            for row in rows]


@check("transaction_log_health")
async def transaction_log_health(ctx):
    # DBCC SQLPERF(LOGSPACE) rather than the Percent Log Used counter 
    # because the counter is only updated on log flushes, which can be delayed by long transactions.
    rows = await ctx.query("""
    SET NOCOUNT ON;
    CREATE TABLE #log (DatabaseName sysname, LogSizeMB float, LogUsedPct float, Status int);
    INSERT INTO #log EXEC (N'DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS');
    SELECT d.name AS DatabaseName, d.log_reuse_wait_desc AS LogReuseWait, l.LogUsedPct,
           CAST(SUM(CASE WHEN mf.type = 1 THEN mf.size ELSE 0 END) * 8 / 1024.0 AS decimal(18, 2)) AS LogSizeMB,
           CAST(SUM(CASE WHEN mf.type = 0 THEN mf.size ELSE 0 END) * 8 / 1024.0 AS decimal(18, 2)) AS DataSizeMB
    FROM sys.databases d
    JOIN #log l ON l.DatabaseName = d.name
    JOIN sys.master_files mf ON mf.database_id = d.database_id
    WHERE d.database_id <> 2 AND d.state_desc = N'ONLINE'
    GROUP BY d.name, d.log_reuse_wait_desc, l.LogUsedPct
    """)
    findings = []
    for row in rows:
        log_mb, data_mb = number(row["LogSizeMB"]) or 0, number(row["DataSizeMB"]) or 0
        # "Large LDF": a log bigger than its data (and over 1 GB) usually means
        # log backups or a long transaction are not letting it truncate.
        oversized = log_mb >= 1024 and log_mb > data_mb
        detail = f"log {log_mb:,.0f} MB, data {data_mb:,.0f} MB; reuse wait {row['LogReuseWait']}"
        if oversized:
            detail += "; log is larger than the data"
        # Percent used swings wildly on tiny logs (msdb's 1 MB log reads 80%
        # between checkpoints), so it is only scored once the log is real.
        used = number(row["LogUsedPct"])
        if log_mb < _MIN_SCORED_LOG_MB:
            detail += f"; under {_MIN_SCORED_LOG_MB} MB, percent not scored"
            used = None
        findings.append(Finding(row["DatabaseName"], round(used, 1) if used is not None else None,
                                database=row["DatabaseName"], detail=detail, floor="WARNING" if oversized else None))
    return findings


@check("maxsize_growth")
async def maxsize_growth(ctx):
    rows = await ctx.query("""
    SELECT DB_NAME(mf.database_id) AS DatabaseName, mf.name AS FileName, mf.type_desc AS FileType,
           CAST(mf.size * 8 / 1024.0 AS decimal(18, 2)) AS SizeMB,
           CAST(mf.max_size * 8 / 1024.0 AS decimal(18, 2)) AS MaxSizeMB,
           CAST(100.0 * mf.size / mf.max_size AS decimal(6, 2)) AS PctOfMax
    FROM sys.master_files mf
    JOIN sys.databases d ON d.database_id = mf.database_id AND d.state_desc = N'ONLINE'
    WHERE mf.max_size > 0 AND mf.growth > 0
        AND NOT (mf.type = 1 AND mf.max_size = 268435456) -- an "unlimited" log file reports a 2 TB cap
    """)
    return [Finding(f"{row['DatabaseName']} {row['FileName']}", number(row["PctOfMax"]), database=row["DatabaseName"],
                    detail=f"{row['FileType']} {row['SizeMB']} of {row['MaxSizeMB']} MB max") for row in rows]


@check("database_growth")
async def database_growth(ctx):
    rows = await ctx.query("""
    SELECT d.name AS DatabaseName, CAST(SUM(CAST(mf.size AS bigint)) * 8 / 1024.0 AS float) AS DataSizeMB
    FROM sys.master_files mf
    JOIN sys.databases d ON d.database_id = mf.database_id
    WHERE mf.type = 0 AND d.database_id <> 2 AND d.state_desc = N'ONLINE'
    GROUP BY d.name
    """)
    sizes = {row["DatabaseName"]: number(row["DataSizeMB"]) or 0.0 for row in rows}
    baseline, baseline_at = ctx.memory.get("sizes"), ctx.memory.get("baseline_at")
    ctx.memory.update(sizes=sizes, baseline_at=ctx.now.isoformat())
    if not baseline or not baseline_at:
        return []
    hours = (ctx.now - datetime.fromisoformat(baseline_at)).total_seconds() / 3600
    if hours < 1:
        return []
    findings = []
    for name, size in sizes.items():
        old = baseline.get(name)
        if not old or size - old < 100:
            continue
        per_day = (size - old) / old * 100 * 24 / hours
        findings.append(Finding(name, round(per_day, 1), database=name,
                                detail=f"{old:,.0f} → {size:,.0f} MB over {hours:.0f} h"))
    return findings


@check("slow_file_growth")
async def slow_file_growth(ctx):
    since = ctx.memory.get("since")
    if since is None:
        ctx.memory["since"] = await server_now(ctx)
        return []
    previous = ctx.memory.get("path")
    previous = "NULL" if not isinstance(previous, str) or len(previous) > 260 else "N'" + previous.replace("'", "''") + "'"

    def growths(path):
        return f"""
        INSERT INTO #g (StartTime, DatabaseName, FileName, EventClass, DurationMs, GrowthMB)
        SELECT t.StartTime, t.DatabaseName, t.FileName, t.EventClass, t.Duration / 1000, CAST(t.IntegerData AS bigint) * 8 / 1024
        FROM sys.fn_trace_gettable({path}, DEFAULT) t
        WHERE t.EventClass IN (92, 93) AND t.StartTime > {as_datetime(since)};"""

    rows = await ctx.query(f"""
    SET NOCOUNT ON;
    DECLARE @path nvarchar(260) = (SELECT [path] FROM sys.traces WHERE is_default = 1);
    DECLARE @previous nvarchar(260) = {previous};
    CREATE TABLE #g (StartTime datetime, DatabaseName nvarchar(256), FileName nvarchar(256), EventClass int,
                     DurationMs bigint, GrowthMB bigint);
    IF @path IS NOT NULL
    BEGIN
        -- After a rollover, read from the file used last time (DEFAULT continues
        -- into the files after it) so events at its tail are not skipped.
        IF @previous IS NOT NULL AND @previous <> @path
        BEGIN
            BEGIN TRY
                {growths("@previous")}
            END TRY
            BEGIN CATCH
                SET @previous = NULL; -- already removed by trace file rotation
            END CATCH;
        END;
        IF @previous IS NULL OR @previous = @path
        BEGIN
            {growths("@path")}
        END;
    END;
    -- The outer row always carries the current path, even with no growth events.
    SELECT p.CurrentPath, g.StartTime, g.StartTimeUtc, g.DatabaseName, g.FileName, g.EventClass, g.DurationMs, g.GrowthMB
    FROM (SELECT @path AS CurrentPath) p
    LEFT JOIN (
        SELECT TOP 200 CONVERT(varchar(23), StartTime, 121) AS StartTime, {TO_UTC.format("StartTime")} AS StartTimeUtc,
               DatabaseName, FileName, EventClass, DurationMs, GrowthMB
        FROM #g
        ORDER BY StartTime
    ) g ON 1 = 1
    ORDER BY g.StartTime;
    """)
    path = next((row["CurrentPath"] for row in rows if row.get("CurrentPath")), None)
    rows = [row for row in rows if row.get("StartTime")]
    if path:
        ctx.memory["path"] = path
    if rows:
        ctx.memory["since"] = max(row["StartTime"] for row in rows)
    return [Occurrence(digest(row["StartTime"], row["DatabaseName"], row["FileName"]), utc(row["StartTimeUtc"], ctx.now),
                       f"{row['DatabaseName']} {row['FileName']}", number(row["DurationMs"]), database=row["DatabaseName"],
                       detail=f"{'data' if row['EventClass'] == 92 else 'log'} file grew {row['GrowthMB']} MB")
            for row in rows]


@check("vlf_count")
async def vlf_count(ctx):
    rows = await ctx.query("""
    SELECT d.name AS DatabaseName, ls.total_vlf_count AS VlfCount
    FROM sys.databases d
    CROSS APPLY sys.dm_db_log_stats(d.database_id) ls
    WHERE d.state_desc = N'ONLINE' AND HAS_DBACCESS(d.name) = 1
    """)
    return [Finding(row["DatabaseName"], number(row["VlfCount"]), database=row["DatabaseName"]) for row in rows]


@check("io_pending")
async def io_pending(ctx):
    rows = await ctx.query("""
    SELECT COUNT(*) AS PendingCount, ISNULL(MAX(io_pending_ms_ticks), 0) AS MaxPendingMs
    FROM sys.dm_io_pending_io_requests
    WHERE io_pending = 1
    """)
    row = rows[0] if rows else {"PendingCount": 0, "MaxPendingMs": 0}
    return [Finding("Pending I/O", number(row["MaxPendingMs"]), detail=f"{row['PendingCount']} request(s) pending")]


@check("slow_disk")
async def slow_disk(ctx):
    rows = await ctx.query("""
    SELECT DB_NAME(vfs.database_id) AS DatabaseName, mf.name AS FileName, mf.type_desc AS FileType,
           vfs.io_stall_read_ms + vfs.io_stall_write_ms AS StallMs, vfs.num_of_reads + vfs.num_of_writes AS IoCount
    FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
    JOIN sys.master_files mf ON mf.database_id = vfs.database_id AND mf.file_id = vfs.file_id
    """)
    current = {f"{row['DatabaseName']}|{row['FileName']}": [number(row["StallMs"]) or 0, number(row["IoCount"]) or 0, row["FileType"]]
               for row in rows if row["DatabaseName"]}
    previous = ctx.memory.get("files")
    ctx.memory["files"] = current
    if previous is None:
        return []
    findings = []
    for key, (stall, count, file_type) in current.items():
        old = previous.get(key)
        if not old:
            continue
        ios, stalled = count - old[1], stall - old[0]
        if ios < 100 or stalled < 0:  # too few I/Os to judge, or counters reset by a restart
            continue
        database, file_name = key.split("|", 1)
        findings.append(Finding(f"{database} {file_name}", round(stalled / ios, 1), database=database,
                                detail=f"{file_type}, {ios:,.0f} I/Os"))
    return findings


_TEMPDB_SPACE = """
SELECT CAST(SUM(total_page_count) * 8 / 1024.0 AS decimal(18, 2)) AS AllocatedMB,
       CAST(SUM(total_page_count - unallocated_extent_page_count) * 8 / 1024.0 AS decimal(18, 2)) AS UsedMB,
       CAST(SUM(version_store_reserved_page_count) * 8 / 1024.0 AS decimal(18, 2)) AS VersionStoreMB,
       CAST(SUM(user_object_reserved_page_count) * 8 / 1024.0 AS decimal(18, 2)) AS UserObjectsMB,
       CAST(SUM(internal_object_reserved_page_count) * 8 / 1024.0 AS decimal(18, 2)) AS InternalObjectsMB
FROM tempdb.sys.dm_db_file_space_usage
"""


async def _tempdb_space(ctx):
    rows = await ctx.cached("tempdb_space", _TEMPDB_SPACE)
    row = rows[0] if rows else {}
    return {key: number(value) or 0.0 for key, value in row.items()}


@check("tempdb_data_utilization")
async def tempdb_data_utilization(ctx):
    space = await _tempdb_space(ctx)
    if not space.get("AllocatedMB"):
        return []
    return [Finding("tempdb data files", round(100 * space["UsedMB"] / space["AllocatedMB"], 1),
                    detail=f"{space['UsedMB']:,.0f} of {space['AllocatedMB']:,.0f} MB; user objects {space['UserObjectsMB']:,.0f} MB, "
                           f"internal {space['InternalObjectsMB']:,.0f} MB, version store {space['VersionStoreMB']:,.0f} MB")]


@check("tempdb_version_store")
async def tempdb_version_store(ctx):
    space = await _tempdb_space(ctx)
    if not space.get("AllocatedMB"):
        return []
    return [Finding("tempdb version store", round(100 * space["VersionStoreMB"] / space["AllocatedMB"], 1),
                    detail=f"{space['VersionStoreMB']:,.0f} MB")]


@check("tempdb_log_usage")
async def tempdb_log_usage(ctx):
    rows = await ctx.query(f"""
    SELECT pc.cntr_value AS LogUsedPct
    FROM sys.dm_os_performance_counters pc
    WHERE {_LOG_USED_COUNTER} AND RTRIM(pc.instance_name) = N'tempdb'
    """)
    return [Finding("tempdb log", number(row["LogUsedPct"])) for row in rows]


@check("tempdb_contention")
async def tempdb_contention(ctx):
    rows = await ctx.query("""
    SELECT COUNT(*) AS WaitingTasks, ISNULL(MAX(wait_duration_ms), 0) AS MaxWaitMs
    FROM sys.dm_os_waiting_tasks
    WHERE wait_type LIKE N'PAGELATCH[_]%' AND resource_description LIKE N'2:%'
    """)
    row = rows[0] if rows else {"WaitingTasks": 0, "MaxWaitMs": 0}
    return [Finding("tempdb PAGELATCH waits", number(row["WaitingTasks"]), detail=f"longest wait {row['MaxWaitMs']} ms")]
