"""
DBA diagnostic tools for Data Eyes MCP Server.

Registers additional @mcp.tool() functions on the same FastMCP instance created
in tools.py, covering the DPA-style diagnostic categories documented in
.claude/knowledge-base/_static/taxonomy.md: wait stats, missing/unused indexes,
stale statistics, live index fragmentation, backup/CHECKDB/job/AG health, and a
per-instance fleet_health_score rollup.

Each tool reimplements the equivalent logic found in
.claude/resources/performance/additional_queries/*.json.sql or .claude/resources/maintenance/diagnostics/*.sql as a
plain (non-FOR-JSON) query built in Python, then formats results via
utils.format_json — mirroring the existing generic tools in tools.py
(schema_discovery, describe_table, etc.), not the .sql files' own
`FOR JSON AUTO` output. FOR JSON AUTO is kept in the .sql files for SSMS/
copy-paste use; over ODBC it can be split across multiple result rows on long
output, which format_json in Python avoids entirely.

Severity thresholds mirror .claude/knowledge-base/_static/thresholds.yaml.
Keep the two in sync manually if thresholds change — see that file's header
for the known drift risk and its mitigation options.
"""

import logging
from typing import Optional, List, Tuple, Any, Dict

from mcp.server.fastmcp import Context

from .tools import mcp, _creds_from_ctx
from .db import execute_query, request_credentials, QueryResult
from .metrics import MetricsContext
from .utils import format_json, escape_sql_string

logger = logging.getLogger(__name__)

# Same exclusion list as .claude/resources/performance/additional_queries/wait_statistics.sql —
# benign/system wait types that don't indicate a performance issue.
_BENIGN_WAIT_TYPES_SQL = """
    N'BROKER_EVENTHANDLER', N'BROKER_RECEIVE_WAITFOR', N'BROKER_TASK_STOP',
    N'BROKER_TO_FLUSH', N'BROKER_TRANSMITTER', N'CHECKPOINT_QUEUE',
    N'CHKPT', N'CLR_AUTO_EVENT', N'CLR_MANUAL_EVENT', N'CLR_SEMAPHORE',
    N'DBMIRROR_DBM_EVENT', N'DBMIRROR_DBM_MUTEX', N'DBMIRROR_EVENTS_QUEUE',
    N'DBMIRROR_WORKER_QUEUE', N'DBMIRRORING_CMD', N'DIRTY_PAGE_POLL',
    N'DISPATCHER_QUEUE_SEMAPHORE', N'EXECSYNC', N'FSAGENT',
    N'FT_IFTS_SCHEDULER_IDLE_WAIT', N'FT_IFTSHC_MUTEX',
    N'HADR_CLUSAPI_CALL', N'HADR_FILESTREAM_IOMGR_IOCOMPLETION',
    N'HADR_LOGCAPTURE_WAIT', N'HADR_NOTIFICATION_DEQUEUE', N'HADR_TIMER_TASK',
    N'HADR_WORK_QUEUE', N'LAZYWRITER_SLEEP', N'LOGMGR_QUEUE',
    N'MEMORY_ALLOCATION_EXT', N'ONDEMAND_TASK_QUEUE',
    N'PREEMPTIVE_HADR_LEASE_MECHANISM', N'PREEMPTIVE_OS_AUTHENTICATIONOPS',
    N'PREEMPTIVE_OS_AUTHORIZATIONOPS', N'PREEMPTIVE_OS_COMOPS',
    N'PREEMPTIVE_OS_CREATEFILE', N'PREEMPTIVE_OS_CRYPTOPS',
    N'PREEMPTIVE_OS_DEVICEOPS', N'PREEMPTIVE_OS_FILEOPS',
    N'PREEMPTIVE_OS_GENERICOPS', N'PREEMPTIVE_OS_LIBRARYOPS',
    N'PREEMPTIVE_OS_PIPEOPS', N'PREEMPTIVE_OS_QUERYREGISTRY',
    N'PREEMPTIVE_OS_VERIFYTRUST', N'PREEMPTIVE_OS_WAITFORSINGLEOBJECT',
    N'PREEMPTIVE_OS_WRITEFILEGATHER', N'PREEMPTIVE_SP_SERVER_DIAGNOSTICS',
    N'PREEMPTIVE_XE_GETTARGETSTATE', N'PWAIT_ALL_COMPONENTS_INITIALIZED',
    N'PWAIT_DIRECTLOGCONSUMER_GETNEXT', N'QDS_ASYNC_QUEUE',
    N'QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP',
    N'QDS_PERSIST_TASK_MAIN_LOOP_SLEEP', N'QDS_SHUTDOWN_QUEUE',
    N'REDO_THREAD_PENDING_WORK', N'REQUEST_FOR_DEADLOCK_SEARCH',
    N'RESOURCE_QUEUE', N'SERVER_IDLE_CHECK', N'SLEEP_BPOOL_FLUSH',
    N'SLEEP_DBSTARTUP', N'SLEEP_DCOMSTARTUP', N'SLEEP_MASTERDBREADY',
    N'SLEEP_MASTERMDREADY', N'SLEEP_MASTERUPGRADED', N'SLEEP_MSDBSTARTUP',
    N'SLEEP_SYSTEMTASK', N'SLEEP_TASK', N'SP_SERVER_DIAGNOSTICS_SLEEP',
    N'SQLTRACE_BUFFER_FLUSH', N'SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
    N'SQLTRACE_WAIT_ENTRIES', N'UCS_SESSION_REGISTRATION',
    N'WAIT_FOR_RESULTS', N'WAIT_XTP_CKPT_CLOSE', N'WAIT_XTP_HOST_WAIT',
    N'WAIT_XTP_OFFLINE_CKPT_NEW_LOG', N'WAIT_XTP_RECOVERY',
    N'WAITFOR', N'WAITFOR_TASKSHUTDOWN', N'XE_TIMER_EVENT',
    N'XE_DISPATCHER_WAIT'
"""


def _severity_rank(sev: Optional[str]) -> int:
    return {"CRITICAL": 0, "WARNING": 1, "OK": 2}.get(sev or "", 3)


def _worst_severity(columns: List[str], rows: List[Tuple[Any, ...]], default: str = "OK") -> str:
    """Worst `severity` value across rows; `default` if the column/rows are absent."""
    if "severity" not in columns or not rows:
        return default
    idx = columns.index("severity")
    worst = default
    for row in rows:
        sev = row[idx]
        if _severity_rank(sev) < _severity_rank(worst):
            worst = sev
    return worst


def _extract_metric(
    columns: List[str], rows: List[Tuple[Any, ...]], column: str, agg: str = "max"
) -> Optional[float]:
    """Pull one representative numeric headline metric out of a diagnostic
    tool's rows — e.g. the worst FullBackupAgeHours across all databases.
    Used only for trend-history snapshots (dashboard/backend/app/collector.py);
    severity remains the authority for health status, this is supplementary
    context for charting a number over time alongside it."""
    if column not in columns or not rows:
        return None
    idx = columns.index(column)
    values = []
    for row in rows:
        v = row[idx]
        if v is None:
            continue
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    if agg == "min":
        return min(values)
    if agg == "count":
        return float(len(values))
    return max(values)


# ---------------------------------------------------------------------------
# SQL builders — shared between each @mcp.tool() and fleet_health_score()
# ---------------------------------------------------------------------------

def _sql_wait_stats(top_n: int) -> str:
    top_n = max(1, min(top_n, 200))
    return f"""
    SELECT TOP {top_n}
        wait_type AS Wait_Type,
        wait_time_ms / 1000.0 AS Wait_Time_Seconds,
        waiting_tasks_count AS Waiting_Tasks_Count,
        wait_time_ms * 100.0 / SUM(wait_time_ms) OVER() AS Percentage_WaitTime,
        CASE
            WHEN wait_time_ms * 100.0 / SUM(wait_time_ms) OVER() >= 25 THEN 'CRITICAL'
            WHEN wait_time_ms * 100.0 / SUM(wait_time_ms) OVER() >= 10 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_os_wait_stats
    WHERE wait_type NOT IN ({_BENIGN_WAIT_TYPES_SQL})
        AND wait_time_ms >= 1
    ORDER BY Wait_Time_Seconds DESC
    """


def _sql_missing_indexes(top_n: int) -> str:
    top_n = max(1, min(top_n, 200))
    return f"""
    SELECT TOP {top_n}
        dm_mid.database_id AS DatabaseID,
        dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) AS Avg_Estimated_Impact,
        dm_migs.last_user_seek AS Last_User_Seek,
        OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) AS TableName,
        'CREATE INDEX [IX_' + OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) + '_'
        + REPLACE(REPLACE(REPLACE(ISNULL(dm_mid.equality_columns,''), ', ', '_'), '[', ''), ']', '')
        + CASE WHEN dm_mid.equality_columns IS NOT NULL AND dm_mid.inequality_columns IS NOT NULL THEN '_' ELSE '' END
        + REPLACE(REPLACE(REPLACE(ISNULL(dm_mid.inequality_columns,''), ', ', '_'), '[', ''), ']', '')
        + ']' + ' ON ' + dm_mid.statement
        + ' (' + ISNULL(dm_mid.equality_columns,'')
        + CASE WHEN dm_mid.equality_columns IS NOT NULL AND dm_mid.inequality_columns IS NOT NULL THEN ',' ELSE '' END
        + ISNULL(dm_mid.inequality_columns, '') + ')'
        + ISNULL(' INCLUDE (' + dm_mid.included_columns + ')', '') AS Create_Statement,
        CASE
            WHEN dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) >= 100000 THEN 'CRITICAL'
            WHEN dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) >= 10000 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_db_missing_index_groups dm_mig
    INNER JOIN sys.dm_db_missing_index_group_stats dm_migs ON dm_migs.group_handle = dm_mig.index_group_handle
    INNER JOIN sys.dm_db_missing_index_details dm_mid ON dm_mig.index_handle = dm_mid.index_handle
    WHERE dm_mid.database_ID = DB_ID()
    ORDER BY Avg_Estimated_Impact DESC
    """


def _sql_unused_indexes(top_n: int) -> str:
    top_n = max(1, min(top_n, 200))
    return f"""
    SELECT TOP {top_n}
        o.name AS ObjectName,
        i.name AS IndexName,
        i.index_id AS IndexID,
        dm_ius.user_seeks AS UserSeek,
        dm_ius.user_scans AS UserScans,
        dm_ius.user_lookups AS UserLookups,
        dm_ius.user_updates AS UserUpdates,
        p.TableRows,
        'DROP INDEX ' + QUOTENAME(i.name) + ' ON ' + QUOTENAME(s.name) + '.'
        + QUOTENAME(OBJECT_NAME(dm_ius.OBJECT_ID)) AS Drop_Statement,
        CASE
            WHEN (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) = 0
                 AND dm_ius.user_updates >= 10000 THEN 'CRITICAL'
            WHEN (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) = 0
                 AND dm_ius.user_updates >= 1 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_db_index_usage_stats dm_ius
    INNER JOIN sys.indexes i ON i.index_id = dm_ius.index_id AND dm_ius.OBJECT_ID = i.OBJECT_ID
    INNER JOIN sys.objects o ON dm_ius.OBJECT_ID = o.OBJECT_ID
    INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
    INNER JOIN (
        SELECT SUM(p.rows) AS TableRows, p.index_id, p.OBJECT_ID
        FROM sys.partitions p GROUP BY p.index_id, p.OBJECT_ID
    ) p ON p.index_id = dm_ius.index_id AND dm_ius.OBJECT_ID = p.OBJECT_ID
    WHERE OBJECTPROPERTY(dm_ius.OBJECT_ID, 'IsUserTable') = 1
        AND dm_ius.database_id = DB_ID()
        AND i.type_desc = 'nonclustered'
        AND i.is_primary_key = 0
        AND i.is_unique_constraint = 0
    ORDER BY (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) ASC
    """


def _sql_stale_statistics(days_threshold: int) -> str:
    days_threshold = max(1, min(days_threshold, 3650))
    return f"""
    SELECT DISTINCT
        OBJECT_NAME(s.[object_id]) AS TableName,
        c.name AS ColumnName,
        s.name AS StatName,
        STATS_DATE(s.[object_id], s.stats_id) AS LastUpdated,
        DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) AS DaysOld,
        dsp.modification_counter AS ModificationCounter,
        CASE
            WHEN DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) >= 60
                 AND dsp.modification_counter >= 1000 THEN 'CRITICAL'
            WHEN DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) >= {days_threshold}
                 AND dsp.modification_counter >= 1 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.stats s
    JOIN sys.stats_columns sc ON sc.[object_id] = s.[object_id] AND sc.stats_id = s.stats_id
    JOIN sys.columns c ON c.[object_id] = sc.[object_id] AND c.column_id = sc.column_id
    JOIN sys.partitions par ON par.[object_id] = s.[object_id]
    JOIN sys.objects obj ON par.[object_id] = obj.[object_id]
    CROSS APPLY sys.dm_db_stats_properties(sc.[object_id], s.stats_id) AS dsp
    WHERE OBJECTPROPERTY(s.OBJECT_ID, 'IsUserTable') = 1
        AND (s.auto_created = 1 OR s.user_created = 1)
    ORDER BY DaysOld DESC
    """


def _sql_index_fragmentation(min_frag_pct: float, top_n: int) -> str:
    top_n = max(1, min(top_n, 500))
    return f"""
    SELECT TOP {top_n}
        DB_NAME(ps.database_id) AS DatabaseName,
        OBJECT_NAME(ps.object_id, ps.database_id) AS TableName,
        i.name AS IndexName,
        ps.index_type_desc AS IndexType,
        ps.avg_fragmentation_in_percent AS FragmentationPct,
        ps.page_count AS PageCount,
        CASE
            WHEN ps.avg_fragmentation_in_percent >= 30 THEN 'CRITICAL'
            WHEN ps.avg_fragmentation_in_percent >= 5 THEN 'WARNING'
            ELSE 'OK'
        END AS severity,
        CASE
            WHEN ps.avg_fragmentation_in_percent >= 30 THEN 'REBUILD'
            WHEN ps.avg_fragmentation_in_percent >= 5 THEN 'REORGANIZE'
            ELSE 'NONE'
        END AS RecommendedAction
    FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ps
    INNER JOIN sys.indexes i ON i.object_id = ps.object_id AND i.index_id = ps.index_id
    WHERE ps.avg_fragmentation_in_percent >= {min_frag_pct}
        AND ps.page_count > 1000
        AND ps.index_id > 0
    ORDER BY ps.avg_fragmentation_in_percent DESC
    """


def _sql_top_queries(top_n: int) -> str:
    top_n = max(1, min(top_n, 200))
    return f"""
    SELECT TOP {top_n}
        DB_NAME(st.dbid) AS DatabaseName,
        qs.execution_count AS ExecutionCount,
        qs.total_elapsed_time / qs.execution_count / 1000.0 AS AvgElapsedTimeMs,
        qs.total_worker_time / qs.execution_count / 1000.0 AS AvgCpuTimeMs,
        qs.total_logical_reads / qs.execution_count AS AvgLogicalReads,
        qs.max_elapsed_time / 1000.0 AS MaxElapsedTimeMs,
        qs.last_execution_time AS LastExecutionTime,
        SUBSTRING(st.text, (qs.statement_start_offset / 2) + 1,
            ((CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset END
                - qs.statement_start_offset) / 2) + 1) AS QueryText,
        CASE
            WHEN qs.total_elapsed_time / qs.execution_count / 1000.0 >= 30000 THEN 'CRITICAL'
            WHEN qs.total_elapsed_time / qs.execution_count / 1000.0 >= 5000 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_exec_query_stats qs
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    WHERE st.dbid IS NOT NULL
    ORDER BY AvgElapsedTimeMs DESC
    """


def _sql_db_space() -> str:
    return """
    SELECT
        db.name AS DatabaseName,
        mf.name AS FileName,
        mf.type_desc AS FileType,
        CAST(mf.size * 8.0 / 1024 AS DECIMAL(18, 2)) AS FileSizeMB,
        CAST((mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024 AS DECIMAL(18, 2)) AS FreeSpaceMB,
        CAST(100.0 * (mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) / NULLIF(mf.size, 0) AS DECIMAL(5, 2)) AS FreeSpacePct,
        CAST(vs.total_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(18, 2)) AS DriveSizeGB,
        CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(18, 2)) AS DriveFreeSpaceGB,
        CASE
            WHEN vs.available_bytes / 1024.0 / 1024 / 1024 < 5 THEN 'CRITICAL'
            WHEN vs.available_bytes / 1024.0 / 1024 / 1024 < 20 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.master_files mf
    INNER JOIN sys.databases db ON db.database_id = mf.database_id
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    WHERE db.database_id > 4 AND db.state_desc = 'ONLINE'
    ORDER BY DriveFreeSpaceGB ASC
    """


def _sql_backup_health() -> str:
    return """
    WITH LastBackups AS (
        SELECT
            database_name,
            MAX(CASE WHEN [type] = 'D' THEN backup_finish_date END) AS LastFullBackup,
            MAX(CASE WHEN [type] = 'I' THEN backup_finish_date END) AS LastDiffBackup,
            MAX(CASE WHEN [type] = 'L' THEN backup_finish_date END) AS LastLogBackup
        FROM msdb.dbo.backupset
        GROUP BY database_name
    )
    SELECT
        d.name AS DatabaseName,
        d.recovery_model_desc AS RecoveryModel,
        lb.LastFullBackup,
        DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) AS FullBackupAgeHours,
        lb.LastDiffBackup,
        lb.LastLogBackup,
        CASE WHEN d.recovery_model_desc <> 'SIMPLE'
             THEN DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) ELSE NULL END AS LogBackupAgeMinutes,
        CASE
            WHEN lb.LastFullBackup IS NULL THEN 'CRITICAL'
            WHEN DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) >= 48 THEN 'CRITICAL'
            WHEN DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) >= 24 THEN 'WARNING'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND lb.LastLogBackup IS NULL THEN 'CRITICAL'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) >= 240 THEN 'CRITICAL'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) >= 60 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.databases d
    LEFT JOIN LastBackups lb ON lb.database_name = d.name
    WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'
    ORDER BY FullBackupAgeHours DESC
    """


def _sql_checkdb_health() -> str:
    return """
    WITH LastCheck AS (
        SELECT DatabaseName, MAX(EndTime) AS LastCheckDBEndTime
        FROM master.dbo.CommandLog
        WHERE CommandType LIKE '%CHECK%'
        GROUP BY DatabaseName
    ),
    SuspectPages AS (
        SELECT database_id, COUNT(*) AS SuspectPageCount
        FROM msdb.dbo.suspect_pages
        WHERE event_type IN (1, 2, 3)
        GROUP BY database_id
    )
    SELECT
        d.name AS DatabaseName,
        lc.LastCheckDBEndTime,
        DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) AS DaysSinceLastCheckDB,
        ISNULL(sp.SuspectPageCount, 0) AS SuspectPageCount,
        CASE
            WHEN ISNULL(sp.SuspectPageCount, 0) > 0 THEN 'CRITICAL'
            WHEN lc.LastCheckDBEndTime IS NULL THEN 'CRITICAL'
            WHEN DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) >= 14 THEN 'CRITICAL'
            WHEN DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) >= 7 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.databases d
    LEFT JOIN LastCheck lc ON lc.DatabaseName = d.name
    LEFT JOIN SuspectPages sp ON sp.database_id = d.database_id
    WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'
    ORDER BY DaysSinceLastCheckDB DESC
    """


def _sql_blocking_snapshot() -> str:
    return """
    SELECT
        r.session_id AS BlockedSessionID,
        r.blocking_session_id AS BlockingSessionID,
        r.wait_type AS WaitType,
        r.wait_time / 1000.0 AS WaitTimeSeconds,
        r.wait_resource AS WaitResource,
        DB_NAME(r.database_id) AS DatabaseName,
        s.login_name AS BlockedLoginName,
        s.host_name AS BlockedHostName,
        st.text AS BlockedQueryText,
        CASE
            WHEN r.blocking_session_id NOT IN (
                SELECT session_id FROM sys.dm_exec_requests WHERE blocking_session_id <> 0
            ) THEN 1 ELSE 0
        END AS BlockingSessionIsHeadBlocker,
        CASE
            WHEN r.wait_time / 1000.0 >= 120 THEN 'CRITICAL'
            WHEN r.wait_time / 1000.0 >= 30 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
    OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st
    WHERE r.blocking_session_id <> 0 AND r.blocking_session_id <> r.session_id
    ORDER BY WaitTimeSeconds DESC
    """


def _sql_ag_health() -> str:
    return """
    SELECT
        DB_NAME(drs.database_id) AS DatabaseName,
        ar.replica_server_name AS Replica,
        drs.synchronization_state_desc AS SyncState,
        drs.synchronization_health_desc AS SyncHealth,
        drs.is_primary_replica AS IsPrimaryReplica,
        drs.log_send_queue_size AS LogSendQueueKB,
        drs.redo_queue_size AS RedoQueueKB,
        CASE
            WHEN drs.synchronization_health_desc = 'NOT_HEALTHY' THEN 'CRITICAL'
            WHEN drs.synchronization_state_desc = 'NOT SYNCHRONIZING' THEN 'CRITICAL'
            WHEN drs.redo_queue_size >= 512000 OR drs.log_send_queue_size >= 512000 THEN 'CRITICAL'
            WHEN drs.synchronization_health_desc = 'PARTIALLY_HEALTHY' THEN 'WARNING'
            WHEN drs.redo_queue_size >= 51200 OR drs.log_send_queue_size >= 51200 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_hadr_database_replica_states drs
    JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id
    WHERE drs.is_local = 1
    ORDER BY DatabaseName
    """


def _sql_job_health() -> str:
    return """
    WITH RecentRuns AS (
        SELECT
            j.job_id,
            j.name AS JobName,
            h.run_status,
            msdb.dbo.agent_datetime(h.run_date, h.run_time) AS RunDateTime,
            h.message AS RunMessage,
            ROW_NUMBER() OVER (PARTITION BY j.job_id ORDER BY msdb.dbo.agent_datetime(h.run_date, h.run_time) DESC) AS rn
        FROM msdb.dbo.sysjobs j
        INNER JOIN msdb.dbo.sysjobhistory h ON h.job_id = j.job_id AND h.step_id = 0
        WHERE j.enabled = 1
    ),
    LastRun AS (SELECT * FROM RecentRuns WHERE rn = 1),
    FailureCounts AS (
        SELECT job_id, COUNT(*) AS FailuresLast7Days
        FROM RecentRuns
        WHERE run_status = 0 AND RunDateTime >= DATEADD(DAY, -7, GETDATE())
        GROUP BY job_id
    )
    SELECT
        lr.JobName,
        lr.RunDateTime AS LastRunDateTime,
        CASE lr.run_status
            WHEN 0 THEN 'Failed' WHEN 1 THEN 'Succeeded' WHEN 2 THEN 'Retry' WHEN 3 THEN 'Canceled' ELSE 'Unknown'
        END AS LastRunStatus,
        lr.RunMessage AS LastRunMessage,
        ISNULL(fc.FailuresLast7Days, 0) AS FailuresLast7Days,
        CASE
            WHEN lr.run_status = 0 THEN 'CRITICAL'
            WHEN ISNULL(fc.FailuresLast7Days, 0) > 0 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM LastRun lr
    LEFT JOIN FailureCounts fc ON fc.job_id = lr.job_id
    ORDER BY LastRunDateTime DESC
    """


async def _run(sql: str, database: Optional[str], ctx: Optional[Context]) -> QueryResult:
    with request_credentials(**_creds_from_ctx(ctx)):
        return await execute_query(sql, database=database)


def _filter_by_database(sql: str, database: Optional[str]) -> str:
    """Append an exact-name filter to the shared WHERE clause anchor used by
    _sql_backup_health / _sql_checkdb_health / _sql_db_space (all scan every
    user database by default; this narrows to one when the caller passes
    `database`)."""
    if not database:
        return sql
    anchor = "WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'"
    return sql.replace(anchor, f"{anchor} AND d.name = {escape_sql_string(database)}")


def _filter_top_queries_by_database(sql: str, database: Optional[str]) -> str:
    """Same idea as _filter_by_database, scoped to _sql_top_queries' own
    WHERE clause anchor (a different shape since it filters plan-cache
    entries by dbid, not sys.databases rows)."""
    if not database:
        return sql
    anchor = "WHERE st.dbid IS NOT NULL"
    return sql.replace(anchor, f"{anchor} AND DB_NAME(st.dbid) = {escape_sql_string(database)}")


# ---------------------------------------------------------------------------
# Public MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def wait_stats(database: Optional[str] = None, top_n: int = 25, ctx: Optional[Context] = None) -> str:
    """
    Analyze SQL Server wait statistics to identify performance bottlenecks.

    Cumulative since last restart / DBCC SQLPERF CLEAR — short-uptime instances
    show noisy percentages. Mirrors .claude/resources/performance/additional_queries/wait_statistics.json.sql.

    Args:
        database: Initial catalog for the connection (waits are instance-wide).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: Wait_Type, Wait_Time_Seconds, Waiting_Tasks_Count,
        Percentage_WaitTime, severity.
    """
    with MetricsContext("wait_stats") as metrics:
        try:
            res = await _run(_sql_wait_stats(top_n), database, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No significant wait statistics found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("wait_stats failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def missing_indexes(database: Optional[str] = None, top_n: int = 25, ctx: Optional[Context] = None) -> str:
    """
    Identify missing indexes by estimated impact, with generated CREATE INDEX text.

    Mirrors .claude/resources/performance/additional_queries/missing_indexes.json.sql. Impact
    thresholds are heuristic — see .claude/knowledge-base/_static/thresholds.yaml.

    Args:
        database: Database to analyze (defaults to the connection's database).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: DatabaseID, Avg_Estimated_Impact, Last_User_Seek, TableName,
        Create_Statement, severity.
    """
    with MetricsContext("missing_indexes") as metrics:
        try:
            res = await _run(_sql_missing_indexes(top_n), database, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No missing indexes reported for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("missing_indexes failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def unused_indexes(database: Optional[str] = None, top_n: int = 25, ctx: Optional[Context] = None) -> str:
    """
    Identify unused nonclustered indexes, with generated DROP INDEX text.

    Caveat: sys.dm_db_index_usage_stats resets on service restart — cross-check
    instance uptime before treating a result here as conclusive. Mirrors
    .claude/resources/performance/additional_queries/unused_indexes.json.sql.

    Args:
        database: Database to analyze (defaults to the connection's database).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: ObjectName, IndexName, IndexID, UserSeek, UserScans,
        UserLookups, UserUpdates, TableRows, Drop_Statement, severity.
    """
    with MetricsContext("unused_indexes") as metrics:
        try:
            res = await _run(_sql_unused_indexes(top_n), database, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No unused indexes found for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("unused_indexes failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def stale_statistics(
    database: Optional[str] = None, days_threshold: int = 30, ctx: Optional[Context] = None
) -> str:
    """
    Find statistics that are stale (old + modified since last update).

    Mirrors .claude/resources/performance/additional_queries/update_statistics.json.sql (the
    read-only analysis half — running sp_updatestats itself is a write
    operation and stays in that original script / .claude/resources/maintenance/).

    Args:
        database: Database to analyze (defaults to the connection's database).
        days_threshold: WARNING threshold in days (default 30, matches
            .claude/knowledge-base/_static/thresholds.yaml index.stats_staleness_days).

    Returns:
        JSON rows: TableName, ColumnName, StatName, LastUpdated, DaysOld,
        ModificationCounter, severity.
    """
    with MetricsContext("stale_statistics") as metrics:
        try:
            res = await _run(_sql_stale_statistics(days_threshold), database, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No statistics found for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("stale_statistics failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def index_fragmentation(
    database: Optional[str] = None,
    min_frag_pct: float = 5.0,
    top_n: int = 50,
    ctx: Optional[Context] = None,
) -> str:
    """
    Live index fragmentation scan (sys.dm_db_index_physical_stats), distinct
    from unused_indexes (usage-stats based). Not a cheap query on large
    databases — don't poll on a short interval. Mirrors
    .claude/resources/maintenance/diagnostics/fragmentation_live_scan.sql.

    Args:
        database: Database to scan (defaults to the connection's database —
            the underlying DMV requires a specific database context).
        min_frag_pct: Minimum fragmentation % to include (default 5.0).
        top_n: Max rows to return (default 50, max 500).

    Returns:
        JSON rows: DatabaseName, TableName, IndexName, IndexType,
        FragmentationPct, PageCount, severity, RecommendedAction.
    """
    with MetricsContext("index_fragmentation") as metrics:
        try:
            res = await _run(_sql_index_fragmentation(min_frag_pct, top_n), database, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No indexes found above the fragmentation threshold."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("index_fragmentation failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def top_queries(database: Optional[str] = None, top_n: int = 25, ctx: Optional[Context] = None) -> str:
    """
    Rank queries by average elapsed time per execution — the "Top SQL"
    DPA-style category. Mirrors .claude/resources/performance/additional_queries/top_queries.json.sql,
    which closed a gap where this logic previously only existed as inline
    Grafana panel SQL.

    Args:
        database: Restrict to queries whose plan is attributed to this
            database (defaults to all databases in the plan cache).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: DatabaseName, ExecutionCount, AvgElapsedTimeMs,
        AvgCpuTimeMs, AvgLogicalReads, MaxElapsedTimeMs, LastExecutionTime,
        QueryText, severity.
    """
    with MetricsContext("top_queries") as metrics:
        try:
            sql = _filter_top_queries_by_database(_sql_top_queries(top_n), database)
            res = await _run(sql, None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No query stats found in the plan cache."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("top_queries failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def db_space(database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Per-file size/free-space plus underlying drive free space — the
    "Storage" DPA-style category. A database can have plenty of free space
    inside its own files while the disk hosting it is nearly full; severity
    is driven by drive free space, the actual outage risk. Mirrors
    .claude/resources/maintenance/diagnostics/db_space_check.sql, which closed a gap where
    this logic previously only existed as inline Grafana panel SQL.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, FileName, FileType, FileSizeMB,
        FreeSpaceMB, FreeSpacePct, DriveSizeGB, DriveFreeSpaceGB, severity.
    """
    with MetricsContext("db_space") as metrics:
        try:
            sql = _filter_by_database(_sql_db_space(), database)
            res = await _run(sql, None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("db_space failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def backup_health(database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Backup health per user database: last FULL/DIFF/LOG backup and staleness.

    Reads msdb.dbo.backupset (any backup method, not just this toolkit's jobs).
    Mirrors .claude/resources/maintenance/diagnostics/backup_health_check.sql.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, RecoveryModel, LastFullBackup,
        FullBackupAgeHours, LastDiffBackup, LastLogBackup,
        LogBackupAgeMinutes (NULL for SIMPLE recovery model), severity.
    """
    with MetricsContext("backup_health") as metrics:
        try:
            sql = _filter_by_database(_sql_backup_health(), database)
            res = await _run(sql, None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("backup_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def checkdb_health(database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    CHECKDB staleness + active suspect pages per user database.

    Reads master.dbo.CommandLog, which only exists once Ola Hallengren's
    maintenance scripts are installed (see .claude/resources/maintenance/README.md) — a database
    never checked via that path reports LastCheckDBEndTime = NULL and
    severity = CRITICAL. Mirrors .claude/resources/maintenance/diagnostics/checkdb_staleness.sql.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, LastCheckDBEndTime, DaysSinceLastCheckDB,
        SuspectPageCount, severity.
    """
    with MetricsContext("checkdb_health") as metrics:
        try:
            sql = _filter_by_database(_sql_checkdb_health(), database)
            res = await _run(sql, None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("checkdb_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def blocking_snapshot(ctx: Optional[Context] = None) -> str:
    """
    Point-in-time snapshot of active blocking, instance-wide, with head-blocker
    identification. This is a snapshot, not a trend — call repeatedly to detect
    persistent vs. transient blocking. Mirrors
    .claude/resources/maintenance/diagnostics/blocking_chain_snapshot.sql.

    Returns:
        JSON rows: BlockedSessionID, BlockingSessionID, WaitType,
        WaitTimeSeconds, WaitResource, DatabaseName, BlockedLoginName,
        BlockedHostName, BlockedQueryText, BlockingSessionIsHeadBlocker, severity.
    """
    with MetricsContext("blocking_snapshot") as metrics:
        try:
            res = await _run(_sql_blocking_snapshot(), None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No active blocking detected."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("blocking_snapshot failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def ag_health(ctx: Optional[Context] = None) -> str:
    """
    Per-database Availability Group sync health — a replica can report HEALTHY
    while one of its databases is NOT SYNCHRONIZING. Returns an empty result
    (not an error) on standalone/non-AG instances. Mirrors
    .claude/resources/maintenance/diagnostics/ag_sync_health.sql.

    Returns:
        JSON rows: DatabaseName, Replica, SyncState, SyncHealth,
        IsPrimaryReplica, LogSendQueueKB, RedoQueueKB, severity. Or a message
        if this instance has no Availability Group configured.
    """
    with MetricsContext("ag_health") as metrics:
        try:
            res = await _run(_sql_ag_health(), None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No Availability Group configured on this instance (standalone)."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("ag_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def job_health(ctx: Optional[Context] = None) -> str:
    """
    Most recent run outcome and 7-day failure count per enabled SQL Agent job.

    Jobs are instance-level, not per-database — this tool has no `database`
    parameter. Mirrors .claude/resources/maintenance/diagnostics/job_failure_scan.sql.

    Returns:
        JSON rows: JobName, LastRunDateTime, LastRunStatus, LastRunMessage,
        FailuresLast7Days, severity.
    """
    with MetricsContext("job_health") as metrics:
        try:
            res = await _run(_sql_job_health(), None, ctx)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No enabled SQL Agent jobs with run history found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("job_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def fleet_health_score(ctx: Optional[Context] = None) -> str:
    """
    Aggregate worst-severity rollup across every diagnostic category for THIS
    instance (wait stats, index fragmentation, disk space, backup, CHECKDB,
    blocking, AG, jobs). True fleet-wide (multi-instance) aggregation happens
    one level up, in the caller (e.g. the dashboard backend fanning out
    across multiple MCP instances) — this tool only ever sees the single
    instance it's connected to. top_queries is deliberately excluded: slow
    queries are an analysis category, not an operational-risk gate the way
    disk exhaustion or a missed backup is.

    Also returns one representative numeric "headline metric" per category
    where one exists (e.g. backup_health's worst FullBackupAgeHours, db_space's
    lowest DriveFreeSpaceGB) — supplementary to severity, used by the
    dashboard's trend-history collector (dashboard/backend/app/collector.py)
    to chart a number over time, not just a status color.

    Returns:
        JSON object: {"overall_severity": ..., "categories": {name: severity, ...},
        "metrics": {"category.column": value, ...}} (metrics omitted where no
        representative numeric column applies or no rows were returned).
    """
    with MetricsContext("fleet_health_score") as metrics_ctx:
        try:
            categories = {
                "wait_stats": _sql_wait_stats(25),
                "index_fragmentation": _sql_index_fragmentation(5.0, 50),
                "db_space": _sql_db_space(),
                "backup_health": _sql_backup_health(),
                "checkdb_health": _sql_checkdb_health(),
                "blocking": _sql_blocking_snapshot(),
                "ag_health": _sql_ag_health(),
                "job_health": _sql_job_health(),
            }
            # (column, aggregation) for each category's headline metric.
            metric_specs = {
                "wait_stats": ("Percentage_WaitTime", "max"),
                "index_fragmentation": ("FragmentationPct", "max"),
                "db_space": ("DriveFreeSpaceGB", "min"),
                "backup_health": ("FullBackupAgeHours", "max"),
                "checkdb_health": ("DaysSinceLastCheckDB", "max"),
                "blocking": ("WaitTimeSeconds", "max"),
                "ag_health": ("RedoQueueKB", "max"),
                "job_health": ("FailuresLast7Days", "max"),
            }

            results = {}
            headline_metrics: Dict[str, float] = {}
            for name, sql in categories.items():
                try:
                    res = await _run(sql, None, ctx)
                    # ag_health legitimately returns nothing on standalone instances —
                    # that's OK, not unknown, so it doesn't drag the rollup down.
                    default = "OK"
                    results[name] = _worst_severity(res.columns, res.rows, default=default)

                    spec = metric_specs.get(name)
                    if spec:
                        column, agg = spec
                        value = _extract_metric(res.columns, res.rows, column, agg)
                        if value is not None:
                            headline_metrics[f"{name}.{column}"] = value
                except Exception:
                    logger.exception("fleet_health_score: category %s failed", name)
                    results[name] = "UNKNOWN"

            rank_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2, "UNKNOWN": 3}
            overall = min(results.values(), key=lambda s: rank_order.get(s, 3)) if results else "UNKNOWN"

            metrics_ctx.set_rows(len(results))
            import json as _json
            return _json.dumps(
                {"overall_severity": overall, "categories": results, "metrics": headline_metrics},
                indent=2,
            )
        except Exception as e:
            logger.exception("fleet_health_score failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"
