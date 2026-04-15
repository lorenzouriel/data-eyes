# SQL Server Performance Tuning — A Step-by-Step Workbook

Most SQL Server performance problems get solved the wrong way: someone notices something is slow, changes a setting or adds an index, and hopes for the best. Sometimes it works. More often it masks the real problem or introduces new ones.

The right approach is methodical. You measure first. You make one change at a time. You measure again.

This article walks through the complete performance tuning methodology from the `performance_tuning_workbook.xlsx` — 10 steps, 16 diagnostic scripts, and reference tables for waits, config, and index maintenance.

---

## Purpose and Scope

A practical, step-by-step workbook to guide SQL Server performance tuning, from baseline to fixes and verification.

**Scope:** Covers on-prem and Azure SQL Managed Instance (many scripts still apply). T-SQL tested on SQL Server 2016+; most work on older versions.

**Pre-requisites:** You need `sysadmin` or `VIEW SERVER STATE` + `VIEW DATABASE STATE`, permission to create Extended Events, and read access to the data/log directories.

**Safety notes:** Avoid blanket fixes. Prefer targeted changes with measurable impact. Be careful with production workloads and long-running operations (index rebuilds, stats fullscan, etc.).

---

## How to Use This Workbook

1. Work through the Checklist top-to-bottom
2. Run the numbered DMV scripts as indicated at each step
3. Log results and decisions in the Baseline_Log (before/after every change)
4. Apply **one change at a time** — measure before and after
5. Use the Waits Guide to map symptoms to likely causes and actions
6. Re-run baselines after each change; keep snapshots by date

---

## The Core Principle

**Measure first. Change one thing at a time. Measure after.**

Without a before picture, you cannot prove a change helped — or catch that it made something else worse. Record every change: who approved it and how you will roll back if needed. Test in lower environments first whenever possible.

---

## The 10-Step Checklist

```
Step 0: Prep
Step 1: Baseline
Step 2: Workload Analysis
Step 3: Contention
Step 4: TempDB
Step 5: Memory
Step 6: CPU
Step 7: I/O and Log
Step 8: Config Review
Step 9: Verify
```

You do not always need all ten steps. Start at Step 1, let the wait statistics tell you where the problem is, and jump to the relevant step. You always end at Step 9.

---

### Step 0 — Prep

**Tasks:**
- Identify environment (server, instance, edition, version, HA/DR). Capture inventory with `01_Server_Inventory`.
- Enable Query Store on target databases (if supported) using `13_Enable_Query_Store`.

**Success criteria:** Inventory captured and stored; Query Store enabled in READ_WRITE mode with sensible limits.

#### 01_Server_Inventory

```sql
SELECT
  SERVERPROPERTY('MachineName')          AS MachineName,
  SERVERPROPERTY('ServerName')           AS ServerName,
  SERVERPROPERTY('Edition')              AS Edition,
  SERVERPROPERTY('ProductVersion')       AS ProductVersion,
  SERVERPROPERTY('ProductLevel')         AS ProductLevel,
  cpu_count,
  hyperthread_ratio,
  scheduler_count,
  numa_node_count,
  physical_memory_kb/1024/1024           AS PhysicalMemoryGB
FROM sys.dm_os_sys_info;
```

#### 13_Enable_Query_Store

Query Store is your long-term memory for query performance. Once enabled, it captures execution plans and runtime statistics so you can see exactly when a query regressed.

```sql
-- Replace YourDB with the database name.
ALTER DATABASE [YourDB] SET QUERY_STORE = ON;
ALTER DATABASE [YourDB] SET QUERY_STORE (
  OPERATION_MODE        = READ_WRITE,
  CLEANUP_POLICY        = (STALE_QUERY_THRESHOLD_DAYS = 30),
  INTERVAL_LENGTH_MINUTES          = 60,
  DATA_FLUSH_INTERVAL_SECONDS      = 900,
  MAX_STORAGE_SIZE_MB              = 2048,
  QUERY_CAPTURE_MODE               = AUTO,
  SIZE_BASED_CLEANUP_MODE          = AUTO
);
```

---

### Step 1 — Baseline

**Tasks:**
- Capture instance configuration with `02_Instance_Config` (save snapshot before any changes)
- Capture file layout and autogrowth with `03_DB_Files_And_Autogrowth` (look for % growth and small fixed increments)
- Capture wait stats with `04_Top_Waits` — save raw numbers, then take a second snapshot after some time and subtract to get deltas
- Capture IO latency by file with `05_IO_Latency_by_File`
- Collect PerfMon counters (see PerfMon Counters section below) continuously over at least 24 hours

Log all results in the **Baseline_Log** before touching anything.

#### 02_Instance_Config

```sql
SELECT name, value, value_in_use, description
FROM sys.configurations
ORDER BY name;
```

#### 03_DB_Files_And_Autogrowth

```sql
SELECT
  DB_NAME(database_id)                   AS database_name,
  type_desc,
  file_id,
  name,
  physical_name,
  size/128                               AS size_mb,
  max_size,
  growth,
  is_percent_growth
FROM sys.master_files
ORDER BY database_name, type_desc, file_id;
```

**Success criteria:** Fixed MB autogrowth and pre-sized files. Percentage-based autogrowth on large databases causes long pauses.

#### 04_Top_Waits

Run once, save. Run again after a period of normal workload and subtract to get meaningful deltas. The wait types at the top of the list tell you where SQL Server is spending time waiting — this is your triage tool.

```sql
WITH waits AS (
  SELECT
    wait_type,
    wait_time_ms - signal_wait_time_ms   AS resource_wait_ms,
    signal_wait_time_ms,
    waiting_tasks_count
  FROM sys.dm_os_wait_stats
  WHERE wait_type NOT IN (
    'SLEEP_TASK','SLEEP_SYSTEMTASK','SQLTRACE_BUFFER_FLUSH','WAITFOR',
    'LOGMGR_QUEUE','CHECKPOINT_QUEUE','REQUEST_FOR_DEADLOCK_SEARCH',
    'XE_TIMER_EVENT','XE_DISPATCHER_WAIT','BROKER_TO_FLUSH','BROKER_TASK_STOP',
    'CLR_SEMAPHORE','FT_IFTS_SCHEDULER_IDLE_WAIT','BROKER_EVENTHANDLER',
    'BROKER_RECEIVE_WAITFOR','DISPATCHER_QUEUE_SEMAPHORE','BROKER_TRANSMITTER',
    'FT_IFTSHC_MUTEX','THREADPOOL','SOS_IDLE_TASK','DIRTY_PAGE_POLL',
    'HADR_FILESTREAM_IOMGR_IOCOMPLETION','SP_SERVER_DIAGNOSTICS_SLEEP',
    'HADR_CLUSAPI_CALL','HADR_LOGCAPTURE_WAIT','HADR_TIMER_TASK',
    'HADR_WORK_QUEUE','HADR_WORKER_QUEUE','HADR_CONNECTIVITY_INFO',
    'WAIT_XTP_HOST_WAIT','WAIT_XTP_OFFLINE_CKPT_NEW_LOG','WAIT_XTP_CKPT_CLOSE',
    'WAIT_XTP_RECOVERY','HADR_FABRIC_CALLBACK','HADR_FABRIC_COMMIT',
    'HADR_FABRIC_SNAPSHOT','BROKER_ENDPOINT_STATE_MUTEX'
  )
)
SELECT TOP 20
  wait_type,
  resource_wait_ms/1000.0                AS resource_wait_s,
  signal_wait_time_ms/1000.0             AS signal_wait_s,
  waiting_tasks_count
FROM waits
ORDER BY resource_wait_ms DESC;
```

#### 05_IO_Latency_by_File

```sql
WITH fs AS (
  SELECT
    DB_NAME(vfs.database_id)            AS db_name,
    mf.physical_name,
    vfs.file_id,
    vfs.num_of_reads,
    vfs.io_stall_read_ms,
    vfs.num_of_writes,
    vfs.io_stall_write_ms,
    vfs.size_on_disk_bytes
  FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
  JOIN sys.master_files AS mf
    ON vfs.database_id = mf.database_id AND vfs.file_id = mf.file_id
)
SELECT
  db_name,
  physical_name,
  CASE WHEN num_of_reads  > 0 THEN 1.0 * io_stall_read_ms  / num_of_reads  ELSE 0 END AS avg_read_ms,
  CASE WHEN num_of_writes > 0 THEN 1.0 * io_stall_write_ms / num_of_writes ELSE 0 END AS avg_write_ms
FROM fs
ORDER BY avg_read_ms DESC, avg_write_ms DESC;
```

**Thresholds:** Data files < 10 ms good, 10–20 ms acceptable, > 20 ms poor. Log files < 5 ms good, 5–10 ms acceptable, > 10 ms poor.

---

### Step 2 — Workload Analysis

**Tasks:**
- Top queries by CPU with `06_Top_Queries_By_CPU`; by reads with `07_Top_Queries_By_Reads`
- Review missing indexes with `08_Missing_Indexes` (avoid dupes, only add high-value indexes)
- Check index usage with `09_Index_Usage` (drop write-heavy unused indexes)
- Check fragmentation with `10_Index_Fragmentation`; rebuild or reorganize as needed

#### 06_Top_Queries_By_CPU

```sql
SELECT TOP 50
  (qs.total_worker_time/1000)                                  AS total_cpu_ms,
  qs.execution_count,
  (qs.total_worker_time/1000) / NULLIF(qs.execution_count,0)  AS avg_cpu_ms,
  (qs.total_elapsed_time/1000)                                 AS total_elapsed_ms,
  (qs.total_elapsed_time/1000) / NULLIF(qs.execution_count,0) AS avg_elapsed_ms,
  qs.total_logical_reads,
  qs.total_logical_reads / NULLIF(qs.execution_count,0)        AS avg_logical_reads,
  qs.creation_time,
  qs.last_execution_time,
  SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
    CASE WHEN qs.statement_end_offset = -1
      THEN LEN(CONVERT(nvarchar(max), st.text))*2
      ELSE (qs.statement_end_offset - qs.statement_start_offset) END /2) AS statement_text,
  DB_NAME(st.dbid)                                             AS database_name,
  qp.query_plan
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle)    AS st
CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) AS qp
ORDER BY qs.total_worker_time DESC;
```

#### 07_Top_Queries_By_Reads

```sql
SELECT TOP 50
  qs.total_logical_reads,
  qs.execution_count,
  qs.total_logical_reads / NULLIF(qs.execution_count,0)        AS avg_logical_reads,
  (qs.total_worker_time/1000)                                  AS total_cpu_ms,
  (qs.total_elapsed_time/1000)                                 AS total_elapsed_ms,
  qs.last_execution_time,
  SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
    CASE WHEN qs.statement_end_offset = -1
      THEN LEN(CONVERT(nvarchar(max), st.text))*2
      ELSE (qs.statement_end_offset - qs.statement_start_offset) END /2) AS statement_text,
  DB_NAME(st.dbid)                                             AS database_name,
  qp.query_plan
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle)    AS st
CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) AS qp
ORDER BY qs.total_logical_reads DESC;
```

#### 08_Missing_Indexes

The `avg_user_impact * (user_seeks + user_scans)` product is your priority score. Higher means the optimizer thinks this index would reduce query cost significantly. **Always check for similar existing indexes before creating new ones.**

```sql
SELECT TOP 25
  mid.database_id,
  DB_NAME(mid.database_id)              AS database_name,
  mid.statement                          AS table_name,
  migs.user_seeks,
  migs.avg_total_user_cost,
  migs.avg_user_impact,
  'CREATE INDEX [IX_missing_' + CONVERT(varchar(16), mig.index_group_handle) + '_' +
       CONVERT(varchar(16), mid.index_handle) + '] ON ' + mid.statement + ' (' +
       ISNULL(mid.equality_columns,'') +
       CASE WHEN mid.inequality_columns IS NULL THEN '' ELSE
            CASE WHEN mid.equality_columns IS NULL THEN '' ELSE ',' END + mid.inequality_columns END +
       ')' +
       ISNULL(' INCLUDE (' + mid.included_columns + ')','') AS create_index_statement
FROM sys.dm_db_missing_index_group_stats AS migs
JOIN sys.dm_db_missing_index_groups      AS mig
  ON migs.group_handle = mig.index_group_handle
JOIN sys.dm_db_missing_index_details     AS mid
  ON mig.index_handle = mid.index_handle
ORDER BY (migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) DESC;
```

#### 09_Index_Usage

Indexes with zero seeks/scans and high `user_updates` are being maintained on every write without being used for reads — pure overhead. **Note:** Usage stats reset on server restart. Check `last_user_seek` before dropping anything.

```sql
-- Run per database (uses DB_ID()).
SELECT
  DB_NAME(database_id)                                 AS db_name,
  OBJECT_SCHEMA_NAME(s.object_id, database_id)         AS schema_name,
  OBJECT_NAME(s.object_id, database_id)                AS object_name,
  i.name                                               AS index_name,
  s.user_seeks, s.user_scans, s.user_lookups, s.user_updates,
  s.last_user_seek, s.last_user_scan, s.last_user_lookup, s.last_user_update
FROM sys.dm_db_index_usage_stats AS s
JOIN sys.indexes AS i
  ON s.object_id = i.object_id AND s.index_id = i.index_id
WHERE database_id = DB_ID()
ORDER BY (s.user_seeks + s.user_scans + s.user_lookups) DESC;
```

#### 10_Index_Fragmentation

```sql
-- Run per database. Adjust mode: LIMITED | SAMPLED | DETAILED
SELECT
  sch.name                                             AS schema_name,
  t.name                                               AS table_name,
  i.name                                               AS index_name,
  ips.index_type_desc,
  ips.avg_fragmentation_in_percent,
  ips.page_count
FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'SAMPLED') AS ips
JOIN sys.indexes AS i   ON ips.object_id = i.object_id AND ips.index_id = i.index_id
JOIN sys.tables  AS t   ON t.object_id = i.object_id
JOIN sys.schemas AS sch ON sch.schema_id = t.schema_id
WHERE ips.page_count > 1000
ORDER BY ips.avg_fragmentation_in_percent DESC;
```

---

### Step 3 — Contention

**Goal:** Identify blocking chains and recurring deadlock patterns. Fix with indexing, batch sizing, or isolation level changes.

High `LCK_*` waits in your baseline point here.

#### 11_Active_Requests_Blocking

```sql
SELECT
  r.session_id,
  r.status,
  r.command,
  r.blocking_session_id,
  r.wait_type,
  r.wait_time,
  r.wait_resource,
  r.cpu_time,
  r.total_elapsed_time,
  r.reads,
  r.writes,
  DB_NAME(r.database_id)                              AS database_name,
  SUBSTRING(t.text, (r.statement_start_offset/2)+1,
    CASE WHEN r.statement_end_offset = -1
      THEN LEN(CONVERT(nvarchar(max), t.text))*2
      ELSE (r.statement_end_offset - r.statement_start_offset) END /2) AS statement_text
FROM sys.dm_exec_requests AS r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) AS t
WHERE r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
```

#### 12_Deadlocks_XE

Create this Extended Events session once and leave it running. Review deadlock graphs regularly to find recurring patterns.

> **This script creates an object on the server.** Adjust the file path to a valid location before running.

```sql
CREATE EVENT SESSION [track_deadlocks] ON SERVER
ADD EVENT sqlserver.xml_deadlock_report
ADD TARGET package0.event_file(
  SET filename=N'C:\XE\deadlocks.xel',
      max_file_size=(50)
)
WITH (
  MAX_MEMORY=4096 KB,
  EVENT_RETENTION_MODE=ALLOW_SINGLE_EVENT_LOSS,
  MAX_DISPATCH_LATENCY=5 SECONDS,
  MAX_EVENT_SIZE=0 KB,
  MEMORY_PARTITION_MODE=NONE,
  TRACK_CAUSALITY=OFF,
  STARTUP_STATE=ON
);
GO
ALTER EVENT SESSION [track_deadlocks] ON SERVER STATE = START;
```

Also check whether Read Committed Snapshot Isolation (RCSI) is enabled — it reduces reader/writer blocking without application changes:

```sql
-- 15_RCSI_Check
SELECT
  name,
  is_read_committed_snapshot_on,
  snapshot_isolation_state_desc
FROM sys.databases;
```

---

### Step 4 — TempDB

High `PAGELATCH_*` waits on `2:1:1` (and nearby pages) indicate TempDB allocation contention. Many sessions are competing for the same allocation bitmap pages.

#### 16_Tempdb_Contention_Check

```sql
SELECT TOP 50 *
FROM sys.dm_os_waiting_tasks
WHERE wait_type LIKE 'PAGELATCH_%'
  AND resource_description LIKE '2:%'
ORDER BY wait_duration_ms DESC;
```

**Fix:** Add TempDB data files — one per logical CPU up to 8, all equal size, all pre-sized. On SQL Server 2016+ no trace flags are needed. Contention gone = PAGELATCH waits on `2:1:*` disappear.

---

### Step 5 — Memory

Three metrics define memory health:

- **Page Life Expectancy (PLE):** How long a page stays in the buffer pool. For modern servers with large RAM, > 1000 seconds is the target. A consistent downward trend means pressure.
- **Memory Grants Pending:** Queries waiting for a memory grant to run sort or hash operations. Should be 0 during normal operations.
- **Buffer Cache Hit Ratio:** Should be > 95%.

`RESOURCE_SEMAPHORE` or `MEMORY_GRANTS_PENDING` waits in your baseline confirm memory grant starvation. Fix: tune the over-granting queries (sort/hash), add memory, or update statistics so estimates are accurate.

---

### Step 6 — CPU

`SOS_SCHEDULER_YIELD` waits mean queries are burning CPU and yielding their scheduler time slice — CPU saturation. `CXPACKET` and `CXCONSUMER` waits indicate parallel query execution that may be causing contention.

Two key settings:

- **MAXDOP:** Start with <= 8 and <= cores per NUMA node. OLTP often benefits from 4–8.
- **Cost Threshold for Parallelism:** The default of 5 is too low for modern hardware. Start at 30–50, then tune by workload.

```sql
EXEC sp_configure 'max degree of parallelism';
EXEC sp_configure 'cost threshold for parallelism';
```

Also run `06_Top_Queries_By_CPU` to find the specific queries driving CPU consumption.

---

### Step 7 — I/O and Log

High `PAGEIOLATCH_SH` / `PAGEIOLATCH_EX` waits = data file reads are slow. High `WRITELOG` waits = the transaction log cannot keep up with write throughput.

Run `05_IO_Latency_by_File` to identify which files are slow. For log issues: pre-size the log file, switch to fixed MB growth, check storage latency, and reduce large transactions.

The best fix for data file I/O is usually **better indexing** — fewer logical reads means fewer physical I/O requests. Hardware upgrades (SSD/NVMe) address the storage ceiling.

---

### Step 8 — Config Review

Run through this checklist quarterly and after any major infrastructure change.

| Setting | Why it matters | Recommended starting point | How to check |
|---|---|---|---|
| max degree of parallelism (MAXDOP) | Limits parallel workers per query | <= 8 and <= cores per NUMA node; OLTP often 4–8 | `EXEC sp_configure 'max degree of parallelism';` |
| cost threshold for parallelism | Threshold for parallel plans | Start 30–50, tune by workload | `EXEC sp_configure 'cost threshold for parallelism';` |
| max server memory (MB) | Caps SQL memory usage | Leave RAM for OS/agents; set an explicit max | `EXEC sp_configure 'max server memory (MB)';` |
| optimize for ad hoc workloads | Reduces plan cache bloat | Enable (1) for ad-hoc heavy workloads | `EXEC sp_configure 'optimize for ad hoc workloads';` |
| backup compression default | Reduces backup IO/time | Enable unless CPU is constrained | `EXEC sp_configure 'backup compression default';` |
| remote admin connections | DAC for emergencies | Enable | `EXEC sp_configure 'remote admin connections';` |
| instant file initialization | Faster data file growth | Grant SQL Server service account "Perform volume maintenance tasks" | OS setting |
| tempdb data files | Reduces allocation contention | #files = CPUs up to 8; equal size; pre-sized | `SELECT * FROM sys.master_files WHERE database_id = 2` |
| database options | Avoids problematic defaults | AUTO_CLOSE OFF, AUTO_SHRINK OFF, PAGE_VERIFY CHECKSUM | `sys.databases` |

---

### Step 9 — Verify

After every change, re-run `04_Top_Waits`. Compare before and after. Log the comparison in the **Baseline_Log**.

If the target wait type went down — success. If a different wait type went up — you have a new problem to investigate. Either way, you have evidence and a paper trail.

**One change at a time. Always.**

---

## Reference: Waits Guide

Use this table to map the top wait type from `04_Top_Waits` to the right step and action.

| Wait Type | Typical Root Cause | What to Check | Actions |
|---|---|---|---|
| CXPACKET / CXCONSUMER | Parallelism skew / too many parallel plans | High parallel workers, low cost threshold | Raise cost threshold, tune queries, cap MAXDOP |
| SOS_SCHEDULER_YIELD | CPU pressure / hot code paths | High CPU%, many runnable tasks | Tune top CPU queries, review MAXDOP |
| PAGEIOLATCH_* | Slow data file reads | High read latency, large scans | Improve indexes, check storage latency, cache warmup |
| WRITELOG | Log write bottleneck | High log flush waits, long transactions | Pre-size log, fixed growth, faster log disk, batch commits |
| LCK_* | Blocking on locks | Blocking trees, low concurrency | Better indexes, shorter transactions, RCSI / appropriate isolation level |
| PAGELATCH_* (tempdb) | TempDB allocation contention | 2:1:1 hotspots | Multiple equally sized tempdb data files, pre-size (trace flags not needed on 2016+) |
| ASYNC_NETWORK_IO | App not consuming results fast enough | Low CPU on server, app-side waits | Fix app fetch pattern, reduce row size |
| RESOURCE_SEMAPHORE / MEMORY_GRANTS_PENDING | Memory grant starvation | Pending grants > 0 | Fix over-granting queries (sort/hash), add memory, update stats |
| THREADPOOL | Worker thread starvation | High connections + blocking | Reduce blocking, cap parallelism, scale out |

---

## Reference: PerfMon Counters

Collect these alongside your SQL DMV data. Aim for a continuous 24-hour sample during a representative workload.

| Counter Path | Why / Notes |
|---|---|
| Processor(_Total)\% Processor Time | Host CPU saturation |
| Process(sqlservr)\% Processor Time | SQL Server CPU share |
| SQLServer:SQL Statistics\Batch Requests/sec | Throughput (higher is busier) |
| SQLServer:SQL Statistics\SQL Compilations/sec | Compilation pressure |
| SQLServer:SQL Statistics\SQL Re-Compilations/sec | Plan instability |
| SQLServer:Buffer Manager\Page life expectancy | Memory pressure (per NUMA node if available) |
| SQLServer:Memory Manager\Memory Grants Pending | Query memory starvation |
| SQLServer:Buffer Manager\Lazy writes/sec | Buffer churn |
| SQLServer:Buffer Manager\Page reads/sec | Read IO volume |
| SQLServer:General Statistics\User Connections | Connection spikes |
| SQLServer:Databases(_Total)\Log Bytes Flushed/sec | Log throughput |
| SQLServer:Databases(_Total)\Log Flushes/sec | Commit rate |
| LogicalDisk(*)\Avg. Disk sec/Read | Read latency per volume |
| LogicalDisk(*)\Avg. Disk sec/Write | Write latency per volume |
| PhysicalDisk(*)\Current Disk Queue Length | Outstanding IOs |
| SQLServer:Access Methods\Full Scans/sec | Large scans (consider indexing) |
| SQLServer:Transactions\Transactions/sec | OLTP intensity |
| SQLServer:Databases(tempdb)\Version Store Size (KB) | Row-version pressure (RCSI/SI) |
| SQLServer:Plan Cache\Cache Hit Ratio | Plan cache health (rough) |

---

## Reference: Index Maintenance Thresholds

| Fragmentation | Action |
|---|---|
| < 5% | Do nothing |
| 5–30% + page_count > 1000 | REORGANIZE + UPDATE STATISTICS (sampled/async) |
| > 30% + page_count > 1000 | REBUILD (online if edition supports) + UPDATE STATISTICS (FULLSCAN for critical predicates) |
| N/A | Update stats on large tables after significant data change (> 20% rows changed) |

---

## Reference: Baseline Log

Record every change here. Include who approved it and how you will roll back.

| Timestamp | Environment | Change Applied | Top 3 Waits (before) | Top 3 Waits (after) | CPU% (before) | CPU% (after) | p95 Query Duration (before) | p95 Query Duration (after) | IO Latency ms/file (before) | IO Latency ms/file (after) | Notes | Approved By |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | |

---

## Meet Your Agentic Performance Tuning Guide

Running the scripts is the easy part. Reading the output, understanding what the numbers mean, knowing which of the ten steps to jump to next — that is where most of the difficulty lies. The scripts tell you what is happening. Knowing what to do about it takes experience.

The `/performance` skill bridges that gap. It reads the actual scripts the moment you invoke it, maps your symptom to the right methodology step, and walks you through the analysis — from "I think something is slow" to "here is the exact query to run and here is what the results mean."

---

### Why Not Just Open the Script?

You could open `04_Top_Waits`, run it in SSMS, and stare at the output. But that raises immediate questions:

- Which wait types are signal and which are background noise?
- Is `CXPACKET` at 35% a problem or expected for this workload?
- Wait stats point to I/O pressure — do I run `08_Missing_Indexes` or `05_IO_Latency_by_File` next?
- What should PLE look like on a server with 256 GB of RAM?
- My `10_Index_Fragmentation` shows 42% fragmentation on 12 tables — do I rebuild all of them right now?

The Waits Guide and reference tables answer these questions — but you have to know to look there, cross-reference the script output, and synthesize a recommendation. That chain of steps is what the skill collapses into a single conversation.

---

### A Real Scenario

It is Monday morning. Users report the application felt slow over the weekend. You do not know where to start.

```
/performance "queries slowed down after the weekend, users are complaining about slow reports"
```

The skill reads `04_Top_Waits`, `06_Top_Queries_By_CPU`, `07_Top_Queries_By_Reads`, and the Waits Guide. It responds:

> **Step 1 → Step 2 — Baseline then Workload**
>
> Weekend degradation after normal weekday performance usually points to one of three things: a plan regression after auto-statistics updates on tables that grew over the week, missing indexes on a table that crossed a size threshold, or a batch job that ran overnight and left locks or fragmentation behind.
>
> Start with wait stats to confirm the bottleneck category. Run `04_Top_Waits`:
>
> **What to look for in the results:**
> - `SOS_SCHEDULER_YIELD` high → CPU saturation. Queries are burning cycles. Go to `06_Top_Queries_By_CPU`.
> - `PAGEIOLATCH_SH` high → data file reads are slow. Check `05_IO_Latency_by_File`, then `08_Missing_Indexes`.
> - `LCK_M_*` high → blocking. A batch job may have left an open transaction. Run `11_Active_Requests_Blocking`.
> - `WRITELOG` high → log I/O bottleneck. Check log file size and growth settings with `03_DB_Files_And_Autogrowth`.
>
> Want me to run this against your server? (yes/no)

You type `yes`. The skill runs `04_Top_Waits` via `sqlcmd`, gets the output, and continues:

> **Results: `SOS_SCHEDULER_YIELD` is 38% of total resource waits. `PAGEIOLATCH_SH` is 29%.**
>
> Both CPU and I/O pressure are present. The most common cause of this combination after a weekend is a plan regression — statistics were auto-updated on a large table Friday night, and the query optimizer chose a different (worse) plan that now does full scans instead of index seeks. This explains both the CPU spike (more work per query) and the I/O increase (more pages read).
>
> Next step: find the top CPU and read-heavy queries. Run `06_Top_Queries_By_CPU` and `07_Top_Queries_By_Reads`. Look at `avg_cpu_ms` and `avg_logical_reads` — a large gap between average and total divided by execution count means the plan changed recently for some executions.
>
> Also check `08_Missing_Indexes` — if a table grew significantly over the weekend, the optimizer may now be recommending a new index it was not recommending before.

In ten minutes you have gone from "something is slow" to a ranked list of suspect queries and index candidates, with the methodology behind each recommendation explained.

---

### How It Works Under the Hood

When you invoke `/performance`, the skill immediately reads all 16 DMV scripts and maps your symptom against the 10-step routing table:

| Your words | Methodology step | Scripts used |
|---|---|---|
| slow queries, not sure where to start, general degradation | Step 1 | `04_Top_Waits` — start here always |
| slow queries, high CPU, scheduler, SOS_SCHEDULER_YIELD | Step 6 | `04_Top_Waits` + `06_Top_Queries_By_CPU` |
| workload, heavy queries, resource consumers | Step 2 | `06_Top_Queries_By_CPU` + `07_Top_Queries_By_Reads` |
| slow reads, IO, full scans, PAGEIOLATCH | Step 7 | `04_Top_Waits` + `05_IO_Latency_by_File` + `08_Missing_Indexes` |
| log, WRITELOG, log growth, log file | Step 7 | `03_DB_Files_And_Autogrowth` + `05_IO_Latency_by_File` |
| blocking, deadlock, lock, sessions | Step 3 | `11_Active_Requests_Blocking` + `15_RCSI_Check` |
| deadlock graph, XE, extended events | Step 3 | `12_Deadlocks_XE` |
| memory, PLE, buffer pool, grants pending | Step 5 | `04_Top_Waits` (RESOURCE_SEMAPHORE) |
| tempdb, pagelatch, 2:1:1 | Step 4 | `16_Tempdb_Contention_Check` |
| plan regression, query store, force plan | Step 2 | `13_Enable_Query_Store` + `14_Query_Store_Top` |
| enable query store | Step 0 | `13_Enable_Query_Store` (**write — confirm before running**) |
| missing indexes, index candidates | Step 2 | `08_Missing_Indexes` |
| unused indexes, write overhead, cleanup | Step 2 | `09_Index_Usage` |
| fragmentation, rebuild, reorganize | Step 2 | `10_Index_Fragmentation` |
| config, MAXDOP, memory settings, cost threshold | Step 8 | `02_Instance_Config` |
| autogrowth, file size, log growth | Step 7 | `03_DB_Files_And_Autogrowth` |
| inventory, version, edition, NUMA | Step 0 | `01_Server_Inventory` |
| verify, after fix, before/after, improvement | Step 9 | re-run `04_Top_Waits` + relevant baseline scripts |
| step N (any number) | directly | script(s) for that step |

If the symptom is ambiguous, the skill asks a clarifying question rather than guessing. It always tells you which step and which script it is using and why.

---

### What This Changes

**Before the skill:** You open `04_Top_Waits`, run it, get output, look up wait type names in documentation, make a judgement call, open the next script, repeat. Each step requires you to hold context from the last step in your head.

**After the skill:** You describe what you are seeing in plain language. The skill reads the scripts, connects your symptom to the right step, presents the relevant query with column-by-column explanation, runs it if you want, and tells you what to do next — including which script to run after, and why.

The methodology does not change. The scripts do not change. What changes is how much cognitive overhead you carry between "something is slow" and "here is the problem and here is the fix."

---

### Invocation Examples

```
/performance "queries slowed down after the weekend, high CPU"
/performance "I'm seeing high CXPACKET waits — what does that mean?"
/performance "find the missing indexes with the highest estimated impact"
/performance "what does RESOURCE_SEMAPHORE tell me about my server?"
/performance "walk me through Step 5 — memory pressure analysis"
/performance "a query regressed after the statistics update last night"
/performance "PLE dropped from 4000 to 200 this morning, what happened?"
/performance "I want to find unused indexes I can safely drop"
/performance "run the full baseline — steps 0 through 1"
/performance "tempdb is hot, PAGELATCH waits on 2:1:1"
/performance "what MAXDOP and cost threshold should I set for an OLTP workload?"
```

All diagnostic scripts (01–11, 13–16) are **read-only** — they query DMVs and system catalogs and change nothing on your server. Script `12_Deadlocks_XE` creates an Extended Events session and will always ask for explicit confirmation before running.

---

*Data Eyes is an open-source SQL Server toolkit. The performance tuning workbook covered in this article lives in the [performance/](https://github.com/lorenzouriel/data-eyes/tree/main/performance) folder of the repository.*
