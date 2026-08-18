"""
DBA diagnostic queries — direct-SQL port of mcp/src/data_eyes_mcp/dba_tools.py.

Same SQL, same severity thresholds (mirrors
.claude/knowledge-base/_static/thresholds.yaml, same as the MCP copy) — this
is a port, not a rewrite, so the dashboard's severities stay identical to
what data-eyes-mcp would compute. The mcp/ copy is left as-is (Claude Code's
sql-server-dba agent still uses it for live interactive diagnosis); keeping
two copies is an accepted, documented drift risk, same shape as the existing
thresholds.yaml-vs-CASE-WHEN-literals note in dba_tools.py's own header.

Unlike dba_tools.py's @mcp.tool() functions (which return formatted text for
an LLM), every function here returns plain Python data — List[Dict[str, Any]]
for row-returning queries (empty list, never a "no rows" message string, when
there's nothing to show — DataTable.tsx already renders that as "No rows."),
or a dict for fleet_health_score. FastAPI serializes these directly; there's
no MCP text-content-block envelope to build.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from . import mssql_client
from .mssql_client import MSSQLError

logger = logging.getLogger(__name__)

# Same exclusion list as performance/additional_queries/wait_statistics.sql /
# mcp/'s dba_tools.py — benign/system wait types that don't indicate a
# performance issue.
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


def _escape_sql_string(value: str) -> str:
    if not value:
        return "''"
    return "'" + value.replace("'", "''") + "'"


def _rows_to_dicts(columns: List[str], rows: List[Tuple[Any, ...]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for row in rows:
        obj: Dict[str, Any] = {}
        for i, col in enumerate(columns):
            value = row[i] if i < len(row) else None
            if isinstance(value, (bytes, bytearray)):
                obj[col] = "<binary>"
            elif hasattr(value, "isoformat"):
                obj[col] = value.isoformat()
            else:
                obj[col] = value
        result.append(obj)
    return result


def _severity_rank(sev: Optional[str]) -> int:
    return {"CRITICAL": 0, "WARNING": 1, "OK": 2}.get(sev or "", 3)


def _worst_severity(rows: List[Dict[str, Any]], default: str = "OK") -> str:
    if not rows:
        return default
    worst = default
    for row in rows:
        sev = row.get("severity")
        if _severity_rank(sev) < _severity_rank(worst):
            worst = sev
    return worst


def _extract_metric(rows: List[Dict[str, Any]], column: str, agg: str = "max") -> Optional[float]:
    """Pull one representative numeric headline metric out of a diagnostic
    result — e.g. the worst FullBackupAgeHours across all databases. Used
    only for trend-history snapshots (app/collector.py); severity remains
    the authority for health status."""
    values = []
    for row in rows:
        v = row.get(column)
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
# SQL builders — identical to mcp/src/data_eyes_mcp/dba_tools.py
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


def _filter_by_database(sql: str, database: Optional[str]) -> str:
    if not database:
        return sql
    anchor = "WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'"
    return sql.replace(anchor, f"{anchor} AND d.name = {_escape_sql_string(database)}")


def _filter_top_queries_by_database(sql: str, database: Optional[str]) -> str:
    if not database:
        return sql
    anchor = "WHERE st.dbid IS NOT NULL"
    return sql.replace(anchor, f"{anchor} AND DB_NAME(st.dbid) = {_escape_sql_string(database)}")


async def _query(connection_string: str, sql: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    res = await mssql_client.execute_query(connection_string, sql, database=database)
    return _rows_to_dicts(res.columns, res.rows)


# ---------------------------------------------------------------------------
# Public functions — one per TAB_BUILDERS entry / fleet_health_score category
# ---------------------------------------------------------------------------

async def wait_stats(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_wait_stats(top_n), database)


async def missing_indexes(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_missing_indexes(top_n), database)


async def unused_indexes(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_unused_indexes(top_n), database)


async def stale_statistics(
    connection_string: str, database: Optional[str] = None, days_threshold: int = 30
) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_stale_statistics(days_threshold), database)


async def index_fragmentation(
    connection_string: str, database: Optional[str] = None, min_frag_pct: float = 5.0, top_n: int = 50
) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_index_fragmentation(min_frag_pct, top_n), database)


async def top_queries(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    sql = _filter_top_queries_by_database(_sql_top_queries(top_n), database)
    return await _query(connection_string, sql)


async def db_space(connection_string: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = _filter_by_database(_sql_db_space(), database)
    return await _query(connection_string, sql)


async def backup_health(connection_string: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = _filter_by_database(_sql_backup_health(), database)
    return await _query(connection_string, sql)


async def checkdb_health(connection_string: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = _filter_by_database(_sql_checkdb_health(), database)
    return await _query(connection_string, sql)


async def blocking_snapshot(connection_string: str) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_blocking_snapshot())


async def ag_health(connection_string: str) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_ag_health())


async def job_health(connection_string: str) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_job_health())


async def list_databases(connection_string: str) -> List[Dict[str, Any]]:
    sql = "SELECT name, database_id, state_desc AS state FROM sys.databases WHERE HAS_DBACCESS(name) = 1 ORDER BY name"
    return await _query(connection_string, sql)


async def fleet_health_score(connection_string: str) -> Dict[str, Any]:
    """Aggregate worst-severity rollup across every diagnostic category for
    THIS instance. top_queries is deliberately excluded: slow queries are an
    analysis category, not an operational-risk gate the way disk exhaustion
    or a missed backup is. Also returns one representative numeric headline
    metric per category where one exists, for app/collector.py's trend
    snapshots."""
    categories_sql = {
        "wait_stats": _sql_wait_stats(25),
        "index_fragmentation": _sql_index_fragmentation(5.0, 50),
        "db_space": _sql_db_space(),
        "backup_health": _sql_backup_health(),
        "checkdb_health": _sql_checkdb_health(),
        "blocking": _sql_blocking_snapshot(),
        "ag_health": _sql_ag_health(),
        "job_health": _sql_job_health(),
    }
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

    results: Dict[str, str] = {}
    headline_metrics: Dict[str, float] = {}
    for name, sql in categories_sql.items():
        try:
            rows = await _query(connection_string, sql)
            # ag_health legitimately returns nothing on standalone instances —
            # that's OK, not unknown, so it doesn't drag the rollup down.
            results[name] = _worst_severity(rows, default="OK")

            spec = metric_specs.get(name)
            if spec:
                column, agg = spec
                value = _extract_metric(rows, column, agg)
                if value is not None:
                    headline_metrics[f"{name}.{column}"] = value
        except MSSQLError:
            logger.exception("fleet_health_score: category %s failed", name)
            results[name] = "UNKNOWN"

    rank_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2, "UNKNOWN": 3}
    overall = min(results.values(), key=lambda s: rank_order.get(s, 3)) if results else "UNKNOWN"

    return {"overall_severity": overall, "categories": results, "metrics": headline_metrics}
