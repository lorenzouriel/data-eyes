"""
The 30-second metric groups: fixed DMV reads exported as Prometheus samples.

Each group returns (metric, value, labels, is_counter) rows. Cumulative values
since instance start are exported as counters; Prometheus computes rates and
handles resets.
"""
import math

from app.sql import query


def metric(name, value, labels=None, counter=False):
    if value is None or not math.isfinite(float(value)):
        return []
    # A NULL from SQL (for example volume_mount_point on Linux) must not reach
    # prometheus_client as None: it fails the whole scrape, not just this sample.
    labels = {key: "" if label is None else str(label) for key, label in (labels or {}).items()}
    return [("data_eyes_" + name, float(value), labels, counter)]


async def resources(connection):
    # Latest scheduler-monitor sample (about one per minute) gives CPU without
    # sampling on our side; a sample older than 3 minutes is not reported.
    [row] = await query(connection, """
    SELECT
        (SELECT CAST(cntr_value AS float) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Buffer cache hit ratio') AS BufferHitRaw,
        (SELECT CAST(cntr_value AS float) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Buffer cache hit ratio base') AS BufferHitBase,
        (SELECT CAST(cntr_value AS float) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') AS PageLifeExpectancy,
        (SELECT CAST(SUM(num_of_bytes_read) AS bigint) FROM sys.dm_io_virtual_file_stats(NULL, NULL)) AS DiskReadBytes,
        (SELECT CAST(cntr_value AS bigint) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Batch Requests/sec') AS BatchRequests,
        (SELECT max_workers_count FROM sys.dm_os_sys_info) AS MaxWorkers,
        (SELECT SUM(current_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS CreatedWorkers,
        (SELECT SUM(current_workers_count - active_workers_count) FROM sys.dm_os_schedulers WHERE status = 'VISIBLE ONLINE') AS IdleWorkers,
        cpu.SampleAgeSeconds, cpu.SqlCpuPct, cpu.SystemIdlePct
    FROM (SELECT 1 AS one) AS anchor
    OUTER APPLY (
        SELECT TOP 1
            ((SELECT ms_ticks FROM sys.dm_os_sys_info) - [timestamp]) / 1000.0 AS SampleAgeSeconds,
            CAST(record AS xml).value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SqlCpuPct,
            CAST(record AS xml).value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS SystemIdlePct
        FROM sys.dm_os_ring_buffers
        WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
        ORDER BY [timestamp] DESC
    ) AS cpu
    """)
    fresh = row["SampleAgeSeconds"] is not None and float(row["SampleAgeSeconds"]) <= 180
    idle = row["SystemIdlePct"] if fresh else None
    hit = round(100.0 * row["BufferHitRaw"] / row["BufferHitBase"], 2) if row["BufferHitRaw"] is not None and row["BufferHitBase"] else None
    return (metric("sql_cpu_pct", row["SqlCpuPct"] if fresh else None)
            + metric("os_cpu_pct", 100 - idle if idle is not None else None)
            + metric("cpu_sample_age_seconds", row["SampleAgeSeconds"])
            + metric("buffer_cache_hit_pct", hit)
            + metric("page_life_expectancy_seconds", row["PageLifeExpectancy"])
            + metric("disk_read_bytes_total", row["DiskReadBytes"], counter=True)
            + metric("batch_requests_total", row["BatchRequests"], counter=True)
            + metric("workers_max", row["MaxWorkers"])
            + metric("workers_created", row["CreatedWorkers"])
            + metric("workers_idle", row["IdleWorkers"]))


async def memory(connection):
    [row] = await query(connection, """
    SELECT
        (SELECT physical_memory_in_use_kb FROM sys.dm_os_process_memory) AS SqlMemoryKB,
        (SELECT CAST(cntr_value AS bigint) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Target Server Memory (KB)') AS TargetMemoryKB,
        (SELECT available_physical_memory_kb FROM sys.dm_os_sys_memory) AS FreeMemoryKB,
        (SELECT page_fault_count FROM sys.dm_os_process_memory) AS PageFaults
    """)
    rows = []
    for column, name in [("SqlMemoryKB", "sql_memory_bytes"), ("TargetMemoryKB", "target_memory_bytes"), ("FreeMemoryKB", "available_memory_bytes")]:
        rows += metric(name, float(row[column]) * 1024 if row[column] is not None else None)
    return rows + metric("page_faults_total", row["PageFaults"], counter=True)


async def io(connection):
    rows = []
    for item in await query(connection, """
    SELECT DB_NAME(vfs.database_id) AS DatabaseName, mf.name AS FileName, vs.volume_mount_point AS Drive,
           CAST(vfs.io_stall_read_ms + vfs.io_stall_write_ms AS float) AS IoStallMs,
           CAST(vfs.num_of_bytes_read + vfs.num_of_bytes_written AS float) AS IoBytes,
           CAST(vfs.num_of_reads + vfs.num_of_writes AS float) AS IoCount
    FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
    JOIN sys.master_files mf ON mf.database_id = vfs.database_id AND mf.file_id = vfs.file_id
    CROSS APPLY sys.dm_os_volume_stats(vfs.database_id, vfs.file_id) vs
    WHERE DB_NAME(vfs.database_id) IS NOT NULL
    """):
        labels = {"database": item["DatabaseName"], "file": item["FileName"], "drive": item["Drive"] or ""}
        for column, name, scale in [("IoStallMs", "io_stall_seconds_total", .001), ("IoBytes", "io_bytes_total", 1), ("IoCount", "io_operations_total", 1)]:
            rows += metric(name, float(item[column]) * scale, labels, True)
    return rows


# Idle and background waits that say nothing about workload pressure.
BENIGN_WAIT_TYPES = (
    "BROKER_EVENTHANDLER", "BROKER_RECEIVE_WAITFOR", "BROKER_TASK_STOP", "BROKER_TO_FLUSH", "BROKER_TRANSMITTER",
    "CHECKPOINT_QUEUE", "CHKPT", "CLR_AUTO_EVENT", "CLR_MANUAL_EVENT", "CLR_SEMAPHORE",
    "DBMIRROR_DBM_EVENT", "DBMIRROR_DBM_MUTEX", "DBMIRROR_EVENTS_QUEUE", "DBMIRROR_WORKER_QUEUE", "DBMIRRORING_CMD",
    "DIRTY_PAGE_POLL", "DISPATCHER_QUEUE_SEMAPHORE", "EXECSYNC", "FSAGENT", "FT_IFTS_SCHEDULER_IDLE_WAIT", "FT_IFTSHC_MUTEX",
    "HADR_CLUSAPI_CALL", "HADR_FILESTREAM_IOMGR_IOCOMPLETION", "HADR_LOGCAPTURE_WAIT", "HADR_NOTIFICATION_DEQUEUE",
    "HADR_TIMER_TASK", "HADR_WORK_QUEUE", "LAZYWRITER_SLEEP", "LOGMGR_QUEUE", "MEMORY_ALLOCATION_EXT", "ONDEMAND_TASK_QUEUE",
    "PREEMPTIVE_HADR_LEASE_MECHANISM", "PREEMPTIVE_OS_AUTHENTICATIONOPS", "PREEMPTIVE_OS_AUTHORIZATIONOPS",
    "PREEMPTIVE_OS_COMOPS", "PREEMPTIVE_OS_CREATEFILE", "PREEMPTIVE_OS_CRYPTOPS", "PREEMPTIVE_OS_DEVICEOPS",
    "PREEMPTIVE_OS_FILEOPS", "PREEMPTIVE_OS_GENERICOPS", "PREEMPTIVE_OS_LIBRARYOPS", "PREEMPTIVE_OS_PIPEOPS",
    "PREEMPTIVE_OS_QUERYREGISTRY", "PREEMPTIVE_OS_VERIFYTRUST", "PREEMPTIVE_OS_WAITFORSINGLEOBJECT",
    "PREEMPTIVE_OS_WRITEFILEGATHER", "PREEMPTIVE_SP_SERVER_DIAGNOSTICS", "PREEMPTIVE_XE_GETTARGETSTATE",
    "PWAIT_ALL_COMPONENTS_INITIALIZED", "PWAIT_DIRECTLOGCONSUMER_GETNEXT", "PWAIT_EXTENSIBILITY_CLEANUP_TASK", "QDS_ASYNC_QUEUE",
    "QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP", "QDS_PERSIST_TASK_MAIN_LOOP_SLEEP", "QDS_SHUTDOWN_QUEUE",
    "REDO_THREAD_PENDING_WORK", "REQUEST_FOR_DEADLOCK_SEARCH", "RESOURCE_QUEUE", "SERVER_IDLE_CHECK", "SLEEP_BPOOL_FLUSH",
    "SLEEP_DBSTARTUP", "SLEEP_DCOMSTARTUP", "SLEEP_MASTERDBREADY", "SLEEP_MASTERMDREADY", "SLEEP_MASTERUPGRADED",
    "SLEEP_MSDBSTARTUP", "SLEEP_SYSTEMTASK", "SLEEP_TASK", "SP_SERVER_DIAGNOSTICS_SLEEP", "SQLTRACE_BUFFER_FLUSH",
    "SQLTRACE_INCREMENTAL_FLUSH_SLEEP", "SQLTRACE_WAIT_ENTRIES", "UCS_SESSION_REGISTRATION", "WAIT_FOR_RESULTS",
    "WAIT_XTP_CKPT_CLOSE", "WAIT_XTP_HOST_WAIT", "WAIT_XTP_OFFLINE_CKPT_NEW_LOG", "WAIT_XTP_RECOVERY", "WAITFOR",
    "WAITFOR_TASKSHUTDOWN", "XE_TIMER_EVENT", "XE_DISPATCHER_WAIT", "SOS_WORK_DISPATCHER",
    "VDI_CLIENT_OTHER", "PARALLEL_REDO_DRAIN_WORKER", "PARALLEL_REDO_WORKER_WAIT_WORK",
)

# Coarse buckets by prefix. Anything else keeps its own wait type as the
# category rather than vanishing into "other".
WAIT_CATEGORIES = [
    (("LCK_", "PAGELATCH_", "LATCH_"), "lock"),
    (("PAGEIOLATCH_", "IO_COMPLETION", "ASYNC_IO_COMPLETION", "WRITELOG", "BACKUPIO"), "disk"),
    (("SOS_SCHEDULER_YIELD", "CXPACKET", "CXCONSUMER", "THREADPOOL"), "cpu"),
    (("ASYNC_NETWORK_IO", "NET_WAITFOR_PACKET"), "network"),
]


def wait_category(wait_type: str) -> str:
    for prefixes, category in WAIT_CATEGORIES:
        if wait_type.startswith(prefixes):
            return category
    return wait_type


async def waits(connection):
    # No top-N window: dropping series would corrupt cumulative counters.
    benign = ", ".join(f"N'{name}'" for name in BENIGN_WAIT_TYPES)
    totals = {}
    for item in await query(connection, f"SELECT wait_type, wait_time_ms / 1000.0 AS seconds FROM sys.dm_os_wait_stats WHERE wait_type NOT IN ({benign})"):
        category = wait_category(item["wait_type"])
        totals[category] = totals.get(category, 0) + float(item["seconds"])
    return [row for category, value in totals.items() for row in metric("wait_seconds_total", value, {"category": category}, True)]


async def counters(connection):
    [row] = await query(connection, """
    SELECT
        (SELECT SUM(cntr_value) FROM sys.dm_os_performance_counters
         WHERE counter_name = 'Number of Deadlocks/sec' AND instance_name = '_Total') AS Deadlocks,
        -- 'Info Errors' are benign and excluded.
        (SELECT SUM(cntr_value) FROM sys.dm_os_performance_counters
         WHERE object_name LIKE '%SQL Errors%'
           AND instance_name IN ('User Errors', 'Kill Connection Errors', 'DB Offline Errors', 'DB Online Errors')) AS Errors
    """)
    return metric("deadlocks_total", row["Deadlocks"], counter=True) + metric("sql_errors_total", row["Errors"], counter=True)


async def activity(connection):
    # is_user_process, not session_id > 50: user sessions can take low ids.
    rows = await query(connection, """
    SELECT DB_NAME(r.database_id) AS db, COUNT(*) AS active,
           SUM(CASE WHEN r.blocking_session_id > 0 THEN 1 ELSE 0 END) AS blocked,
           MAX(CASE WHEN r.blocking_session_id > 0 THEN r.wait_time ELSE 0 END) / 1000.0 AS longest_wait
    FROM sys.dm_exec_requests r
    JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
    WHERE r.session_id <> @@SPID AND s.is_user_process = 1
    GROUP BY r.database_id
    """)
    result = metric("blocked_sessions", sum(item["blocked"] for item in rows))
    result += metric("blocking_max_wait_seconds", max((float(item["longest_wait"]) for item in rows), default=0))
    for item in rows:
        result += metric("active_requests", item["active"], {"database": item["db"] or "unknown"})
    return result


async def databases(connection):
    """Every 5 minutes: database state, size, access mode and Always On role,
    plus server facts and free space per volume. Text is exported as labels on
    info gauges (value 1); names come from the server and are low-cardinality."""
    rows = await query(connection, """
    SELECT d.name AS db, d.state AS state, s.size_bytes,
           CAST(DATABASEPROPERTYEX(d.name, 'Updateability') AS nvarchar(60)) AS updateability,
           ag.name AS availability_group, ars.role_desc AS replica_role
    FROM sys.databases d
    OUTER APPLY (SELECT SUM(CAST(m.size AS bigint)) * 8192 AS size_bytes FROM sys.master_files m WHERE m.database_id = d.database_id) s
    LEFT JOIN sys.availability_replicas ar ON ar.replica_id = d.replica_id
    LEFT JOIN sys.availability_groups ag ON ag.group_id = ar.group_id
    LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.replica_id = d.replica_id AND ars.is_local = 1
    """)
    result = []
    for item in rows:
        labels = {"database": item["db"]}
        result += metric("database_state", item["state"], labels)
        result += metric("database_size_bytes", item["size_bytes"], labels)
        result += metric("database_info", 1, {**labels, "updateability": item["updateability"] or "",
                                              "availability_group": item["availability_group"] or "",
                                              "replica_role": item["replica_role"] or ""})
    [server] = await query(connection, """
    SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS ProductVersion,
           CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) AS Edition,
           CAST(SERVERPROPERTY('MachineName') AS nvarchar(128)) AS MachineName,
           (SELECT cpu_count FROM sys.dm_os_sys_info) AS Cores,
           (SELECT physical_memory_kb FROM sys.dm_os_sys_info) AS MemoryKB
    """)
    result += metric("server_info", 1, {"version": server["ProductVersion"] or "", "edition": server["Edition"] or "",
                                        "machine": server["MachineName"] or ""})
    result += metric("server_cores", server["Cores"])
    result += metric("server_memory_bytes", float(server["MemoryKB"]) * 1024 if server["MemoryKB"] is not None else None)
    for volume in await query(connection, """
    SELECT DISTINCT vs.volume_mount_point AS Drive, vs.available_bytes AS FreeBytes, vs.total_bytes AS TotalBytes
    FROM sys.master_files mf
    JOIN sys.databases d ON d.database_id = mf.database_id AND d.state_desc = N'ONLINE'
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    """):
        result += metric("volume_free_bytes", volume["FreeBytes"], {"drive": volume["Drive"]})
        result += metric("volume_size_bytes", volume["TotalBytes"], {"drive": volume["Drive"]})
    return result


# (group, function, seconds between runs or None for the collector interval)
GROUPS = [("resources", resources, None), ("memory", memory, None), ("io", io, None), ("waits", waits, None),
          ("counters", counters, None), ("activity", activity, None), ("databases", databases, 300)]
