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
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from . import mssql_client
from .mssql_client import MSSQLError

logger = logging.getLogger(__name__)

# Same exclusion list as .claude/resources/performance/additional_queries/wait_statistics.sql /
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
    N'XE_DISPATCHER_WAIT', N'SOS_WORK_DISPATCHER'
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
                # Hex-encoded (e.g. "0xABCD...") rather than an opaque
                # placeholder — plan_handle in particular needs to round-trip
                # through the API as a real, usable identifier (see
                # query_plan()), and a hex string is more useful than
                # "<binary>" for any other varbinary column too.
                obj[col] = "0x" + bytes(value).hex()
            elif hasattr(value, "isoformat"):
                obj[col] = value.isoformat()
            else:
                obj[col] = value
        result.append(obj)
    return result


def _severity_rank(sev: Optional[str]) -> int:
    return {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "OK": 3}.get(sev or "", 2)


def _worst_severity(rows: List[Dict[str, Any]], default: str = "OK") -> str:
    if not rows:
        return default
    worst = default
    for row in rows:
        sev = row.get("severity") or "UNKNOWN"
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
        'OK' AS severity -- Wait distribution is informational, not a distress threshold.
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
        qs.plan_handle AS PlanHandle,
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
        vs.volume_mount_point AS Drive,
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
        CASE WHEN d.group_database_id IS NOT NULL
             THEN 'Local replica history only; missing or stale records require verification on other replicas'
             ELSE 'Local backup history' END AS BackupEvidence,
        lb.LastFullBackup,
        DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) AS FullBackupAgeHours,
        lb.LastDiffBackup,
        lb.LastLogBackup,
        CASE WHEN d.recovery_model_desc <> 'SIMPLE'
             THEN DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) ELSE NULL END AS LogBackupAgeMinutes,
        CASE
            WHEN d.group_database_id IS NOT NULL AND (
                lb.LastFullBackup IS NULL OR DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) >= 24
                OR (d.recovery_model_desc <> 'SIMPLE' AND (lb.LastLogBackup IS NULL
                    OR DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) >= 60))
            ) THEN 'UNKNOWN' -- Other replicas may hold the backup history.
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
    rows = await _query(connection_string, _sql_wait_stats(top_n), database)
    for row in rows:
        row["Category"] = categorize_wait_type(str(row.get("Wait_Type", "")))
    return rows


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


_SQL_FILE_IO_STATS = """
SELECT
    DB_NAME(vfs.database_id) AS DatabaseName,
    mf.name AS FileName,
    vs.volume_mount_point AS Drive,
    CAST(vfs.io_stall_read_ms + vfs.io_stall_write_ms AS FLOAT) AS IoStallMs,
    CAST(vfs.num_of_bytes_read + vfs.num_of_bytes_written AS FLOAT) AS IoBytes,
    CAST(vfs.num_of_reads + vfs.num_of_writes AS FLOAT) AS IoCount
FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
INNER JOIN sys.master_files mf ON mf.database_id = vfs.database_id AND mf.file_id = vfs.file_id
CROSS APPLY sys.dm_os_volume_stats(vfs.database_id, vfs.file_id) vs
WHERE DB_NAME(vfs.database_id) IS NOT NULL
"""


async def file_io_stats(connection_string: str) -> List[Dict[str, Any]]:
    """Cumulative-since-restart IO stall time, bytes transferred, and IO
    count per data/log file, with its drive (volume_mount_point) — same
    dm_os_volume_stats join _sql_db_space() uses for free space. Cumulative,
    so app/collector.py diffs this between cycles (same delta technique as
    wait_stats -> wait_category_snapshot) rather than persisting it as-is."""
    return await _query(connection_string, _SQL_FILE_IO_STATS)


_SQL_WORKER_STATS = """
SELECT
    (SELECT max_workers_count FROM sys.dm_os_sys_info) AS MaxWorkers,
    (SELECT SUM(current_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS CreatedWorkers,
    (SELECT SUM(current_workers_count - active_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS IdleWorkers
"""


async def worker_stats(connection_string: str) -> Dict[str, Any]:
    """Worker thread pool pressure — max configured, currently created, and
    idle (created but not doing work right now). Point-in-time gauges, same
    shape as resource_utilization's buffer-cache gauges."""
    rows = await _query(connection_string, _SQL_WORKER_STATS)
    return rows[0] if rows else {}


_SQL_MEMORY_STATS = """
SELECT
    (SELECT physical_memory_in_use_kb FROM sys.dm_os_process_memory) AS SqlMemoryKB,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Target Server Memory (KB)') AS TargetMemoryKB,
    (SELECT available_physical_memory_kb FROM sys.dm_os_sys_memory) AS FreeMemoryKB,
    (SELECT page_fault_count FROM sys.dm_os_process_memory) AS PageFaults
"""


async def memory_stats(connection_string: str) -> Dict[str, Any]:
    """SQL Server's own memory footprint (physical_memory_in_use), its
    configured target, and OS-level free physical memory — point-in-time
    gauges, not cumulative counters."""
    rows = await _query(connection_string, _SQL_MEMORY_STATS)
    return rows[0] if rows else {}


_SQL_ERROR_COUNTERS = """
SELECT SUM(cntr_value) AS ErrorCount
FROM sys.dm_os_performance_counters
WHERE object_name LIKE '%SQL Errors%'
    AND instance_name IN ('User Errors', 'Kill Connection Errors', 'DB Offline Errors', 'DB Online Errors')
"""


async def error_rate_stats(connection_string: str) -> Optional[float]:
    """Cumulative-since-restart count of meaningful SQL Server errors —
    excludes the benign 'Info Errors' instance, same exclusion-list
    philosophy as _BENIGN_WAIT_TYPES_SQL's benign wait types. Only
    meaningful as a rate: app/collector.py diffs this between cycles, same
    delta technique as resource_utilization's disk/batch counters, and
    derives a severity from the delta (0 = OK, some errors = WARNING/CRITICAL)."""
    rows = await _query(connection_string, _SQL_ERROR_COUNTERS)
    if not rows:
        return None
    value = rows[0].get("ErrorCount")
    return float(value) if value is not None else None


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


async def database_status(connection_string: str) -> List[Dict[str, Any]]:
    """Database access mode and local Always On membership, including unreadable replicas."""
    return await _query(connection_string, """
        SELECT d.name, d.state_desc AS state,
            CAST(DATABASEPROPERTYEX(d.name, 'Updateability') AS nvarchar(60)) AS updateability,
            CAST(CASE WHEN d.group_database_id IS NULL THEN 0 ELSE 1 END AS bit) AS in_availability_group,
            ag.name AS availability_group,
            ars.role_desc AS replica_role
        FROM sys.databases d
        LEFT JOIN sys.availability_replicas ar ON ar.replica_id = d.replica_id
        LEFT JOIN sys.availability_groups ag ON ag.group_id = ar.group_id
        LEFT JOIN sys.dm_hadr_availability_replica_states ars
            ON ars.replica_id = d.replica_id AND ars.is_local = 1
        ORDER BY d.name
    """)


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

    rank_order = {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "OK": 3}
    overall = min(results.values(), key=lambda s: rank_order.get(s, 3)) if results else "UNKNOWN"

    return {"overall_severity": overall, "categories": results, "metrics": headline_metrics}


# ---------------------------------------------------------------------------
# Strata design additions — instance-level detail views (wait categorization,
# sessions, server facts, resource gauges, execution plans). Same
# plain-function-returning-plain-data shape as everything above.
# ---------------------------------------------------------------------------

_WAIT_CATEGORY_PREFIXES: List[Tuple[Tuple[str, ...], str]] = [
    (("LCK_", "PAGELATCH_", "LATCH_"), "lock"),
    (("PAGEIOLATCH_", "IO_COMPLETION", "ASYNC_IO_COMPLETION", "WRITELOG", "BACKUPIO"), "disk"),
    (("SOS_SCHEDULER_YIELD", "CXPACKET", "CXCONSUMER", "THREADPOOL"), "cpu"),
    (("ASYNC_NETWORK_IO", "NET_WAITFOR_PACKET"), "network"),
]


def categorize_wait_type(wait_type: str) -> str:
    """Buckets a raw sys.dm_os_wait_stats wait_type into the 4 coarse
    categories the Waits tab groups by (lock / disk / cpu / network) where a
    prefix is recognized. Anything else is surfaced as the actual wait_type
    — never collapsed into a generic "other" bucket, since that hid
    whatever was really driving wait time behind an opaque catch-all. Shared
    by wait_stats' category column and app/collector.py's historical
    wait-category sampling — one taxonomy, not two."""
    for prefixes, category in _WAIT_CATEGORY_PREFIXES:
        if any(wait_type.startswith(p) for p in prefixes):
            return category
    return wait_type


def _sql_active_sessions(top_n: int) -> str:
    top_n = max(1, min(top_n, 200))
    return f"""
    SELECT TOP {top_n}
        s.session_id AS Pid,
        st.text AS SqlText,
        s.login_name AS LoginName,
        s.program_name AS ProgramName,
        s.host_name AS HostName,
        DB_NAME(r.database_id) AS DatabaseName,
        r.plan_handle AS PlanHandle,
        COALESCE(r.wait_type, r.status, s.status) AS State,
        COALESCE(r.wait_time, 0) / 1000.0 AS WaitSeconds,
        COALESCE(r.total_elapsed_time, 0) / 1000.0 AS ElapsedSeconds
    FROM sys.dm_exec_sessions s
    LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id
    OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st
    WHERE s.is_user_process = 1 AND s.session_id <> @@SPID
    ORDER BY CASE WHEN r.session_id IS NULL THEN 1 ELSE 0 END, r.total_elapsed_time DESC, s.session_id
    """


async def active_sessions(connection_string: str, top_n: int = 50) -> List[Dict[str, Any]]:
    """Connected user sessions, including idle connections — not a history;
    call again to see how it's changed. Same DMV family as blocking_snapshot,
    without the blocking filter."""
    return await _query(connection_string, _sql_active_sessions(top_n))


_SQL_SERVER_OVERVIEW = """
SELECT
    CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS ProductVersion,
    CAST(SERVERPROPERTY('Edition') AS NVARCHAR(128)) AS Edition,
    CAST(SERVERPROPERTY('MachineName') AS NVARCHAR(128)) AS MachineName,
    (SELECT cpu_count FROM sys.dm_os_sys_info) AS Cores,
    (SELECT CAST(physical_memory_kb / 1024.0 / 1024 AS DECIMAL(10,1)) FROM sys.dm_os_sys_info) AS TotalMemoryGB,
    (
        SELECT CAST(SUM(total_bytes) / 1024.0 / 1024 / 1024 AS DECIMAL(10,1))
        FROM (
            SELECT DISTINCT vs.volume_mount_point, vs.total_bytes
            FROM sys.master_files mf
            CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
        ) v
    ) AS TotalDiskGB
"""


async def server_overview(connection_string: str) -> Dict[str, Any]:
    """Static-ish server facts (version, host, cores, total memory/disk) —
    powers the Fleet Status row-expand and Admin's instance table."""
    rows = await _query(connection_string, _SQL_SERVER_OVERVIEW)
    return rows[0] if rows else {}


_SQL_BUFFER_GAUGES = """
SELECT
    (SELECT CAST(cntr_value AS FLOAT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Buffer cache hit ratio') AS BufferHitRaw,
    (SELECT CAST(cntr_value AS FLOAT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Buffer cache hit ratio base') AS BufferHitBase,
    (SELECT CAST(cntr_value AS FLOAT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') AS PageLifeExpectancySeconds
"""

_SQL_CPU_HISTORY = """
SELECT TOP 20
    timestamp AS TimestampMs,
    CAST(record AS XML).value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS CpuPct,
    CAST(record AS XML).value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS SystemIdlePct
FROM sys.dm_os_ring_buffers
WHERE ring_buffer_type = 'RING_BUFFER_SCHEDULER_MONITOR'
ORDER BY timestamp DESC
"""

_SQL_RATE_COUNTERS = """
SELECT
    (SELECT CAST(SUM(num_of_bytes_read) AS BIGINT) FROM sys.dm_io_virtual_file_stats(NULL, NULL)) AS DiskReadBytesTotal,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Batch Requests/sec') AS BatchRequestsTotal
"""


async def resource_utilization(connection_string: str) -> Dict[str, Any]:
    """Current resource gauges for the Resources tab.

    Buffer cache hit % and Page Life Expectancy are true point-in-time
    gauges — no history needed to know "now". CPU % history comes free from
    SQL Server's own scheduler-monitor ring buffer (~4h at ~1min resolution,
    no collection needed on our side). Disk read bytes and batch requests
    are *cumulative* counters since instance start — meaningless as a single
    number, so this returns the raw totals for app/collector.py to diff
    between cycles into an actual rate; a live "current" MB/s or requests/sec
    figure only exists once at least two collector samples have landed.
    """
    gauges_rows = await _query(connection_string, _SQL_BUFFER_GAUGES)
    gauges = gauges_rows[0] if gauges_rows else {}
    buffer_hit_raw = gauges.get("BufferHitRaw")
    buffer_hit_base = gauges.get("BufferHitBase")
    buffer_cache_hit_pct = (
        round(100.0 * buffer_hit_raw / buffer_hit_base, 2)
        if buffer_hit_raw is not None and buffer_hit_base
        else None
    )

    cpu_rows = await _query(connection_string, _SQL_CPU_HISTORY)
    cpu_history = list(reversed(cpu_rows))  # oldest first, for charting
    latest_cpu = cpu_rows[0] if cpu_rows else {}
    system_idle_pct = latest_cpu.get("SystemIdlePct")
    # SQL Server's own share of CPU vs. the OS total (SQL + every other
    # process) — the ring buffer's SystemIdle is OS-wide idle %, so
    # 100 - SystemIdle is total OS utilization, of which ProcessUtilization
    # is SQL Server's slice.
    os_cpu_pct = (100 - system_idle_pct) if system_idle_pct is not None else None

    rate_rows = await _query(connection_string, _SQL_RATE_COUNTERS)
    raw_counters = rate_rows[0] if rate_rows else {}

    return {
        "buffer_cache_hit_pct": buffer_cache_hit_pct,
        "page_life_expectancy_seconds": gauges.get("PageLifeExpectancySeconds"),
        "cpu_history": cpu_history,
        "sql_cpu_pct": latest_cpu.get("CpuPct"),
        "os_cpu_pct": os_cpu_pct,
        "disk_read_bytes_total": raw_counters.get("DiskReadBytesTotal"),
        "batch_requests_total": raw_counters.get("BatchRequestsTotal"),
    }


_PLAN_HANDLE_RE = re.compile(r"^0x[0-9A-Fa-f]+$")

_SHOWPLAN_NS = "{http://schemas.microsoft.com/sqlserver/2004/07/showplan}"


def _find_relops(elem, depth: int = 0) -> List[Tuple[Any, int]]:
    """Yield every <RelOp> in document order with its nesting depth, walking
    into each RelOp's operator-specific child (<Hash>, <NestedLoops>, ...) to
    find the RelOps it contains one level deeper."""
    out: List[Tuple[Any, int]] = []
    for child in elem:
        if child.tag == f"{_SHOWPLAN_NS}RelOp":
            out.append((child, depth))
            out.extend(_find_relops(child, depth + 1))
        else:
            out.extend(_find_relops(child, depth))
    return out


def _direct_child_relops(elem) -> List[Any]:
    out = []
    for child in elem:
        if child.tag == f"{_SHOWPLAN_NS}RelOp":
            out.append(child)
        else:
            out.extend(c for c in child if c.tag == f"{_SHOWPLAN_NS}RelOp")
    return out


def _subtree_cost(elem) -> float:
    try:
        return float(elem.get("EstimatedTotalSubtreeCost", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_plan_xml(xml_text: str, avg_elapsed_ms: float) -> List[Dict[str, Any]]:
    """Parse SQL Server's ShowPlan XML into a flat, depth-ordered operator
    list with each node's own (non-subtree) share of the plan's total
    estimated cost, used to allocate the query's real average elapsed time
    proportionally across operators.

    This is cost-based attribution — the same technique SSMS's estimated
    plan view uses, applied to the actual cached plan for this statement.
    It is NOT independently measured per-operator runtime: SQL Server only
    exposes that via Query Store's actual-execution statistics or live
    Extended Events tracing, neither of which this reads. The `estimated_
    time_ms` field name is deliberate — never rename it to imply it was
    measured.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("query_plan: could not parse plan XML")
        return []

    relops = _find_relops(root)
    if not relops:
        return []

    total_cost = _subtree_cost(relops[0][0]) or 1.0  # first RelOp in document order is the plan root

    nodes = []
    for elem, depth in relops:
        own_cost = _subtree_cost(elem) - sum(_subtree_cost(c) for c in _direct_child_relops(elem))
        own_cost = max(own_cost, 0.0)
        share = (own_cost / total_cost) if total_cost else 0.0
        nodes.append(
            {
                "depth": depth,
                "physical_op": elem.get("PhysicalOp", "?"),
                "logical_op": elem.get("LogicalOp", "?"),
                "estimated_rows": elem.get("EstimateRows"),
                "cost_share": round(share, 4),
                "estimated_time_ms": round(share * avg_elapsed_ms, 2),
            }
        )
    return nodes


_SQL_QUERY_PLAN = """
SELECT
    qs.execution_count AS ExecutionCount,
    qs.total_elapsed_time AS TotalElapsedTimeMicros,
    qs.total_logical_reads AS TotalLogicalReads,
    CAST(qp.query_plan AS NVARCHAR(MAX)) AS QueryPlanXml
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
WHERE qs.plan_handle = {plan_handle}
"""


async def query_plan(connection_string: str, plan_handle: str) -> Dict[str, Any]:
    """Real execution plan for one cached statement, parsed into a
    cost-proportional per-node time breakdown — see _parse_plan_xml's
    docstring for exactly what "real" means here (cost-derived, not
    measured). `plan_handle` must be the hex string top_queries() returns
    (e.g. "0x0500...") — validated strictly since it's embedded directly
    into the query (mssql_client runs fixed, parameter-free SQL)."""
    if not _PLAN_HANDLE_RE.match(plan_handle):
        raise MSSQLError(f"Invalid plan_handle: {plan_handle!r}")

    rows = await _query(connection_string, _SQL_QUERY_PLAN.format(plan_handle=plan_handle))
    if not rows or not rows[0].get("QueryPlanXml"):
        return {"available": False, "nodes": []}

    row = rows[0]
    execution_count = max(int(row.get("ExecutionCount") or 1), 1)
    avg_elapsed_ms = (row.get("TotalElapsedTimeMicros") or 0) / execution_count / 1000.0
    avg_logical_reads = (row.get("TotalLogicalReads") or 0) / execution_count

    return {
        "available": True,
        "execution_count": execution_count,
        "avg_elapsed_ms": round(avg_elapsed_ms, 2),
        "avg_logical_reads": round(avg_logical_reads, 1),
        "nodes": _parse_plan_xml(row["QueryPlanXml"], avg_elapsed_ms),
    }


_SQL_HEALTH_RING_BUFFER = """
SELECT xet.target_data AS TargetData
FROM sys.dm_xe_session_targets xet
JOIN sys.dm_xe_sessions xes ON xes.address = xet.event_session_address
WHERE xes.name = 'system_health' AND xet.target_name = 'ring_buffer'
"""


def _parse_deadlock_events(xml_text: str) -> List[Dict[str, Any]]:
    """Shreds the system_health Extended Events ring buffer's XML for
    xml_deadlock_report events — same xml.etree.ElementTree technique
    _parse_plan_xml() uses for query plans, applied to a different schema (a
    deadlock graph's <process>/<resource-list>, not <RelOp>). Best-effort:
    SQL Server's deadlock XML shape has minor version-to-version variance, so
    every field read here degrades to None rather than raising if a
    particular attribute is absent."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("deadlock_events: could not parse system_health ring buffer XML")
        return []

    events: List[Dict[str, Any]] = []
    for event in root.findall(".//event[@name='xml_deadlock_report']"):
        deadlock = event.find(".//deadlock")
        if deadlock is None:
            continue

        processes = {p.get("id"): p for p in deadlock.findall("./process-list/process")}
        victim_ids = [v.get("id") for v in deadlock.findall("./victim-list/victimProcess")]
        victim = processes.get(victim_ids[0]) if victim_ids else None

        resource_parts = []
        for res in deadlock.findall("./resource-list/*"):
            label = res.get("objectname") or res.get("associatedObjectId") or res.get("waitresource")
            resource_parts.append(f"{res.tag}{': ' + label if label else ''}")

        victim_login = victim.get("loginname") if victim is not None else None
        victim_host = victim.get("hostname") if victim is not None else None
        events.append(
            {
                "occurred_at": event.get("timestamp"),
                "database_name": victim.get("currentdbname") if victim is not None else None,
                "victim_login": victim_login,
                "victim_host": victim_host,
                "victim_program": victim.get("clientapp") if victim is not None else None,
                "resource_description": "; ".join(resource_parts) or None,
                "process_count": len(processes),
                "summary": f"{len(processes)} process(es) — victim {victim_login or 'unknown'}@{victim_host or 'unknown'}",
            }
        )
    return events


async def deadlock_events(connection_string: str) -> List[Dict[str, Any]]:
    """Deadlock graphs currently held in SQL Server's own system_health
    Extended Events ring buffer (always-on by default — no new XE session is
    created, this only reads one that already exists) — read-only, same
    DMV-only philosophy as everything else in this module. The ring buffer
    has limited capacity and rolls over, so app/collector.py polls this and
    persists new events into deadlock_event for durable history."""
    rows = await _query(connection_string, _SQL_HEALTH_RING_BUFFER)
    if not rows or not rows[0].get("TargetData"):
        return []
    return _parse_deadlock_events(rows[0]["TargetData"])
