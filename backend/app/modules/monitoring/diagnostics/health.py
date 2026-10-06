"""Health implementation."""

import re
from typing import Any, Dict, List, Optional, Tuple
from app.modules.monitoring.diagnostics.common import _filter_by_database
from app.modules.monitoring.diagnostics.common import _query
from app.modules.monitoring.diagnostics.queries import _sql_ag_health
from app.modules.monitoring.diagnostics.queries import _sql_backup_health
from app.modules.monitoring.diagnostics.queries import _sql_checkdb_health
from app.modules.monitoring.diagnostics.queries import _sql_db_space
from app.modules.monitoring.diagnostics.queries import _sql_job_health


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


_SQL_WORKER_STATS = """
SELECT
    (SELECT max_workers_count FROM sys.dm_os_sys_info) AS MaxWorkers,
    (SELECT SUM(current_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS CreatedWorkers,
    (SELECT SUM(current_workers_count - active_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS IdleWorkers
"""


_SQL_MEMORY_STATS = """
SELECT
    (SELECT physical_memory_in_use_kb FROM sys.dm_os_process_memory) AS SqlMemoryKB,
    (SELECT CAST(cntr_value AS BIGINT) FROM sys.dm_os_performance_counters
     WHERE counter_name = 'Target Server Memory (KB)') AS TargetMemoryKB,
    (SELECT available_physical_memory_kb FROM sys.dm_os_sys_memory) AS FreeMemoryKB,
    (SELECT page_fault_count FROM sys.dm_os_process_memory) AS PageFaults
"""


_SQL_ERROR_COUNTERS = """
SELECT SUM(cntr_value) AS ErrorCount
FROM sys.dm_os_performance_counters
WHERE object_name LIKE '%SQL Errors%'
    AND instance_name IN ('User Errors', 'Kill Connection Errors', 'DB Offline Errors', 'DB Online Errors')
"""


async def backup_health(connection_string: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = _filter_by_database(_sql_backup_health(), database)
    return await _query(connection_string, sql)


async def checkdb_health(connection_string: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = _filter_by_database(_sql_checkdb_health(), database)
    return await _query(connection_string, sql)


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


_WAIT_CATEGORY_PREFIXES: List[Tuple[Tuple[str, ...], str]] = [
    (("LCK_", "PAGELATCH_", "LATCH_"), "lock"),
    (("PAGEIOLATCH_", "IO_COMPLETION", "ASYNC_IO_COMPLETION", "WRITELOG", "BACKUPIO"), "disk"),
    (("SOS_SCHEDULER_YIELD", "CXPACKET", "CXCONSUMER", "THREADPOOL"), "cpu"),
    (("ASYNC_NETWORK_IO", "NET_WAITFOR_PACKET"), "network"),
]


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


_PLAN_HANDLE_RE = re.compile(r"^0x[0-9A-Fa-f]+$")


_SHOWPLAN_NS = "{http://schemas.microsoft.com/sqlserver/2004/07/showplan}"


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


_SQL_HEALTH_RING_BUFFER = """
SELECT xet.target_data AS TargetData
FROM sys.dm_xe_session_targets xet
JOIN sys.dm_xe_sessions xes ON xes.address = xet.event_session_address
WHERE xes.name = 'system_health' AND xet.target_name = 'ring_buffer'
"""
