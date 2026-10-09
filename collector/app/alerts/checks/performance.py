"""Performance and activity: CPU, memory, workers, blocking, queries, errors."""

import re
from collections import Counter

from app.alerts.checks.backups import parse_error_header
from app.alerts.checks.registry import check
from app.alerts.checks.registry import digest
from app.alerts.checks.registry import for_each_database
from app.alerts.checks.registry import number
from app.alerts.checks.registry import read_error_log
from app.alerts.checks.registry import utc
from app.alerts.models import Finding
from app.alerts.models import Occurrence


@check("cpu_utilization")
async def cpu_utilization(ctx):
    rows = await ctx.query("""
    SELECT TOP 5
        rb.record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SqlCpuPct,
        100 - rb.record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS TotalCpuPct
    FROM (
        SELECT [timestamp], CONVERT(xml, record) AS record
        FROM sys.dm_os_ring_buffers
        WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR' AND record LIKE N'%<SystemHealth>%'
          AND [timestamp] >= (SELECT ms_ticks FROM sys.dm_os_sys_info) - 180000
    ) rb
    ORDER BY rb.[timestamp] DESC
    """)
    totals = [number(row["TotalCpuPct"]) for row in rows if row["TotalCpuPct"] is not None]
    if not totals:
        return [Finding("CPU", floor="UNKNOWN", detail="No recent CPU sample")]
    sql = [number(row["SqlCpuPct"]) or 0 for row in rows]
    return [Finding("CPU", round(sum(totals) / len(totals), 1),
                    detail=f"SQL Server {sum(sql) / len(sql):.0f}% of the 5-sample average")]


@check("memory_available")
async def memory_available(ctx):
    rows = await ctx.query("""
    SELECT available_physical_memory_kb / 1024 AS AvailableMB, total_physical_memory_kb / 1024 AS TotalMB,
           system_memory_state_desc AS MemoryState
    FROM sys.dm_os_sys_memory
    """)
    return [Finding("Physical memory", number(row["AvailableMB"]), detail=f"of {row['TotalMB']:,} MB; {row['MemoryState']}",
                    floor="WARNING" if "low" in (row["MemoryState"] or "").lower() else None) for row in rows]


@check("page_life_expectancy")
async def page_life_expectancy(ctx):
    rows = await ctx.query("""
    SELECT cntr_value AS PageLifeExpectancy
    FROM sys.dm_os_performance_counters
    WHERE object_name LIKE N'%Buffer Manager%' AND counter_name = N'Page life expectancy'
    """)
    return [Finding("Buffer pool", number(row["PageLifeExpectancy"])) for row in rows]


@check("memory_grants_pending")
async def memory_grants_pending(ctx):
    rows = await ctx.query("""
    SELECT cntr_value AS GrantsPending
    FROM sys.dm_os_performance_counters
    WHERE object_name LIKE N'%Memory Manager%' AND counter_name = N'Memory Grants Pending'
    """)
    return [Finding("Memory grants", number(row["GrantsPending"])) for row in rows]


@check("threadpool_exhaustion")
async def threadpool_exhaustion(ctx):
    rows = await ctx.query("""
    SELECT si.max_workers_count AS MaxWorkers,
           (SELECT SUM(active_workers_count) FROM sys.dm_os_schedulers WHERE status = N'VISIBLE ONLINE') AS ActiveWorkers,
           (SELECT COUNT(*) FROM sys.dm_os_waiting_tasks WHERE wait_type = N'THREADPOOL') AS ThreadpoolWaits
    FROM sys.dm_os_sys_info si
    """)
    findings = []
    for row in rows:
        maximum, active, waits = number(row["MaxWorkers"]) or 0, number(row["ActiveWorkers"]) or 0, number(row["ThreadpoolWaits"]) or 0
        findings.append(Finding("Worker threads", round(100 * active / maximum, 1) if maximum else None,
                                detail=f"{active:,.0f} of {maximum:,.0f} active; {waits:,.0f} task(s) waiting on THREADPOOL",
                                floor="CRITICAL" if waits > 0 else None))
    return findings


@check("blocking")
async def blocking(ctx):
    rows = await ctx.query("""
    SELECT r.session_id AS BlockedSessionId, r.blocking_session_id AS BlockingSessionId,
           DB_NAME(r.database_id) AS DatabaseName, r.wait_type AS WaitType, r.wait_time / 1000.0 AS WaitSeconds,
           s.login_name AS LoginName, s.host_name AS HostName
    FROM sys.dm_exec_requests r
    JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
    WHERE r.blocking_session_id <> 0 AND r.blocking_session_id <> r.session_id
    """)
    return [Finding(f"Session {row['BlockedSessionId']} blocked by {row['BlockingSessionId']}", number(row["WaitSeconds"]),
                    database=row["DatabaseName"], detail=f"{row['WaitType']}; {row['LoginName']}@{row['HostName']} in {row['DatabaseName']}")
            for row in rows]


@check("long_running_process")
async def long_running_process(ctx):
    rows = await ctx.query("""
    SELECT r.session_id AS SessionId, DB_NAME(r.database_id) AS DatabaseName, r.command AS Command,
           s.login_name AS LoginName, s.program_name AS ProgramName, r.total_elapsed_time / 1000.0 AS ElapsedSeconds
    FROM sys.dm_exec_requests r
    JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
    WHERE s.is_user_process = 1 AND r.session_id <> @@SPID
        AND ISNULL(r.wait_type, N'') NOT IN (N'WAITFOR', N'BROKER_RECEIVE_WAITFOR', N'TRACEWRITE',
                                             N'SP_SERVER_DIAGNOSTICS_SLEEP', N'XE_LIVE_TARGET_TVF')
        AND r.command NOT IN (N'BACKUP DATABASE', N'BACKUP LOG', N'RESTORE DATABASE', N'RESTORE LOG', N'DBCC', N'WAITFOR')
    """)
    return [Finding(f"Session {row['SessionId']}", number(row["ElapsedSeconds"]), database=row["DatabaseName"],
                    detail=f"{row['Command']} by {row['LoginName']} ({row['ProgramName'] or 'unknown program'})")
            for row in rows]


@check("slow_queries")
async def slow_queries(ctx):
    # Pick the top 10 first, then resolve text for those 10 only: applying
    # dm_exec_sql_text before TOP resolves every recent plan in a large cache.
    rows = await ctx.query("""
    SELECT DB_NAME(st.dbid) AS DatabaseName, OBJECT_NAME(st.objectid, st.dbid) AS ObjectName,
           qs.Executions, qs.AvgElapsedMs,
           CONVERT(varchar(18), qs.query_hash, 1) AS QueryHash
    FROM (
        SELECT TOP 10 sql_handle, query_hash, execution_count AS Executions,
               total_elapsed_time / execution_count / 1000.0 AS AvgElapsedMs
        FROM sys.dm_exec_query_stats
        WHERE last_execution_time >= DATEADD(MINUTE, -15, GETDATE()) AND execution_count > 0
        ORDER BY total_elapsed_time / execution_count DESC
    ) qs
    OUTER APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    ORDER BY qs.AvgElapsedMs DESC
    OPTION (MAXDOP 1)
    """)
    return [Finding(row["ObjectName"] or f"Query {row['QueryHash']}", round(number(row["AvgElapsedMs"]) or 0, 1),
                    database=row["DatabaseName"], detail=f"{row['Executions']:,} executions; avg elapsed")
            for row in rows]


@check("query_regression")
async def query_regression(ctx):
    rows = await ctx.query(for_each_database(
        "SELECT DB_NAME(), COUNT(*) FROM sys.dm_db_tuning_recommendations "
        "WHERE type = N'FORCE_LAST_GOOD_PLAN' AND (state LIKE N'%\"currentValue\":\"Active\"%' "
        "OR state LIKE N'%\"currentValue\":\"Verifying\"%') HAVING COUNT(*) > 0",
        "DatabaseName sysname, Regressions int",
        where="is_query_store_on = 1",
    ))
    return [Finding(row["DatabaseName"], number(row["Regressions"]), database=row["DatabaseName"],
                    detail="see sys.dm_db_tuning_recommendations") for row in rows]


# Severity 20 network/handshake noise from scanners and clients, and failed
# logins (their own alert), are not database errors.
_IGNORED_ERRORS = {823, 824, 825, 17806, 17832, 17835, 17836, 18452, 18456}


@check("database_errors")
async def database_errors(ctx):
    rows = await read_error_log(ctx, "Severity:")
    parsed = []
    for row in rows or []:
        header = parse_error_header(row["Text"])
        if header and header[1] >= 17 and header[0] not in _IGNORED_ERRORS:
            parsed.append((row, header))
    templates = {}
    numbers = sorted({header[0] for _, header in parsed})
    if numbers:
        found = await ctx.query("SELECT message_id AS MessageId, LEFT(text, 200) AS MessageText FROM sys.messages "
                                f"WHERE language_id = 1033 AND message_id IN ({', '.join(str(int(n)) for n in numbers)})")
        templates = {row["MessageId"]: row["MessageText"] for row in found}
    return [Occurrence(digest(row["LogDate"], row["ProcessInfo"], row["Text"]), utc(row["LogDateUtc"], ctx.now), f"Error {error}",
                       detail=f"severity {severity}, state {state}, {row['ProcessInfo']} at {row['LogDate']} (server time)"
                              + (f": {templates[error]}" if templates.get(error) else ""),
                       floor="CRITICAL" if severity >= 20 else "WARNING")
            for row, (error, severity, state) in parsed[:50]]


_LOGIN = re.compile(r"Login failed for user '([^']*)'")
_CLIENT = re.compile(r"\[CLIENT: ([^\]]+)\]")


@check("login_failed")
async def login_failed(ctx):
    rows = await read_error_log(ctx, "Login failed", limit=5000)
    if not rows:
        return []
    users = Counter((_LOGIN.search(row["Text"]) or [None, "?"])[1] for row in rows)
    clients = Counter((_CLIENT.search(row["Text"]) or [None, "?"])[1] for row in rows)
    top = lambda counter: ", ".join(f"{name or '(blank)'} ({count})" for name, count in counter.most_common(3))
    last = max(row["LogDate"] for row in rows)
    return [Occurrence(f"through:{last}", utc(max(row["LogDateUtc"] for row in rows), ctx.now), "Failed logins", float(len(rows)),
                       detail=f"since previous check; users {top(users)}; clients {top(clients)}")]
