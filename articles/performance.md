# A Structured Approach to SQL Server Performance Tuning

Most SQL Server performance problems get solved the wrong way: someone notices something is slow, changes a setting or creates an index, and hopes for the best. Sometimes it works. More often, it masks the real problem or introduces new ones.

The right approach is methodical. You measure first. You make one change at a time. You measure again.

This article walks through a 9-step performance tuning methodology and the four diagnostic scripts that support it — a complete, repeatable framework for finding and fixing SQL Server bottlenecks.

---

## The Core Principle

Before touching anything: **measure first, change one thing at a time, measure after.**

This sounds obvious, but most performance investigations skip the baseline step. Without a before picture, you cannot prove that your change actually helped — or notice that it made something else worse.

---

## What the Toolkit Includes

```
performance/
├── performance_tuning_workbook.xlsx     # Planning and tracking workbook
└── additional_queries/
    ├── wait_statistics.sql              # Bottleneck identification
    ├── missing_indexes.sql              # Index impact analysis
    ├── unused_indexes.sql               # Index cleanup candidates
    ├── update_statistics.sql            # Stale statistics detection
    └── docs/
        ├── wait_statistics.md
        ├── missing_indexes.md
        ├── unused_indexes.md
        └── update_statistics.md
```

The workbook provides the planning framework. The SQL scripts are your diagnostic tools. The documentation files explain what to do with the results.

---

## The 9-Step Methodology

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

You do not always need all nine steps. You start at Step 1, let the wait statistics tell you where the problem is, and jump to the relevant step. But you always end at Step 9.

---

### Step 0 — Prep

Before measuring anything, document your environment:

- SQL Server version and edition
- CPU count and NUMA topology
- Total RAM and `max server memory` setting
- Database count and rough sizes
- Whether Query Store is enabled (if SQL Server 2016+)

Enable Query Store if it is not already on:

```sql
ALTER DATABASE [YourDatabase] SET QUERY_STORE = ON;
ALTER DATABASE [YourDatabase] SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    INTERVAL_LENGTH_MINUTES = 60,
    MAX_STORAGE_SIZE_MB = 1000,
    QUERY_CAPTURE_MODE = AUTO
);
```

Query Store is your long-term memory for query performance. Once enabled, it captures execution plans and runtime statistics so you can see exactly when a query regressed.

---

### Step 1 — Baseline

Run `wait_statistics.sql`. This is your starting point for every performance investigation.

```sql
SELECT TOP 20
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    max_wait_time_ms,
    signal_wait_time_ms,
    ROUND(100.0 * wait_time_ms / SUM(wait_time_ms) OVER (), 2) AS pct_total
FROM sys.dm_os_wait_stats
WHERE wait_type NOT IN (
    -- Exclude benign wait types
    'SLEEP_TASK', 'BROKER_TO_FLUSH', 'BROKER_TASK_STOP',
    'CLR_AUTO_EVENT', 'DISPATCHER_QUEUE_SEMAPHORE',
    'FT_IFTS_SCHEDULER_IDLE_WAIT', 'HADR_WORK_QUEUE',
    'ONDEMAND_TASK_QUEUE', 'REQUEST_FOR_DEADLOCK_SEARCH',
    'RESOURCE_QUEUE', 'SERVER_IDLE_CHECK', 'SLEEP_DBSTARTUP',
    'SLEEP_DCOMSTARTUP', 'SLEEP_MASTERDBREADY', 'SLEEP_MASTERMDREADY',
    'SLEEP_MASTERUPGRADED', 'SLEEP_MSDBSTARTUP', 'SLEEP_SYSTEMTASK',
    'SLEEP_TEMPDBSTARTUP', 'SNI_HTTP_ACCEPT', 'SP_SERVER_DIAGNOSTICS_SLEEP',
    'SQLTRACE_BUFFER_FLUSH', 'SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
    'WAITFOR', 'XE_DISPATCHER_WAIT', 'XE_TIMER_EVENT'
)
ORDER BY wait_time_ms DESC;
```

The wait types at the top of this list tell you where SQL Server is spending time waiting. This is your triage tool. Record these numbers — they are your baseline.

**Reading the results:**

| Wait type | Indicates |
|---|---|
| `CXPACKET` / `CXCONSUMER` | Parallelism — go to Step 6 |
| `LCK_M_*` | Locking/blocking — go to Step 3 |
| `PAGEIOLATCH_*` | Disk I/O — go to Step 7 |
| `PAGELATCH_*` | TempDB contention — go to Step 4 |
| `RESOURCE_SEMAPHORE` | Memory grants — go to Step 5 |
| `SOS_SCHEDULER_YIELD` | CPU pressure — go to Step 6 |
| `WRITELOG` | Log I/O bottleneck — go to Step 7 |

Log your results in the **Baseline_Log** tab of the workbook.

---

### Step 2 — Workload Analysis

Find the worst-performing queries and the indexes they need.

#### Finding Missing Indexes

`missing_indexes.sql` queries the `sys.dm_db_missing_index_*` DMVs. SQL Server tracks every time the query optimizer would have benefited from an index that does not exist:

```sql
SELECT TOP 25
    dm_mid.database_id AS DatabaseID,
    dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) AS Avg_Estimated_Impact,
    dm_migs.last_user_seek AS Last_User_Seek,
    OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) AS [TableName],
    'CREATE INDEX [IX_' + OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) + '...]'
        + ' ON ' + dm_mid.statement
        + ' (' + ISNULL(dm_mid.equality_columns, '')
        + ISNULL(',' + dm_mid.inequality_columns, '') + ')'
        + ISNULL(' INCLUDE (' + dm_mid.included_columns + ')', '') AS Create_Index_Statement
FROM sys.dm_db_missing_index_details dm_mid
INNER JOIN sys.dm_db_missing_index_groups dm_mig ON dm_mid.index_handle = dm_mig.index_handle
INNER JOIN sys.dm_db_missing_index_group_stats dm_migs ON dm_mig.index_group_handle = dm_migs.group_handle
ORDER BY Avg_Estimated_Impact DESC;
```

The `Avg_Estimated_Impact` column is your priority score. Higher means the query optimizer thinks this index would reduce query cost significantly.

**Important caveats:**
- The generated `CREATE INDEX` statement is a recommendation, not a command to copy-paste blindly
- Check for similar existing indexes before creating new ones — you may only need to add columns to an existing index
- Every index adds write overhead — do not create indexes on highly write-heavy tables without measuring the tradeoff

#### Finding Unused Indexes

`unused_indexes.sql` queries `sys.dm_db_index_usage_stats`. Each index that SQL Server never reads is pure overhead — it slows down inserts, updates, and deletes while providing no benefit to queries:

```sql
SELECT TOP 25
    OBJECT_NAME(i.object_id) AS TableName,
    i.name AS IndexName,
    i.type_desc,
    s.user_seeks,
    s.user_scans,
    s.user_lookups,
    s.user_updates,
    s.last_user_seek,
    s.last_user_scan
FROM sys.indexes i
LEFT JOIN sys.dm_db_index_usage_stats s
    ON i.object_id = s.object_id
    AND i.index_id = s.index_id
    AND s.database_id = DB_ID()
WHERE OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1
    AND i.index_id > 1
    AND (s.user_seeks = 0 OR s.user_seeks IS NULL)
    AND (s.user_scans = 0 OR s.user_scans IS NULL)
ORDER BY s.user_updates DESC;
```

Indexes with zero seeks/scans and high `user_updates` are the clearest candidates for removal — they are being maintained on every write without being used for any read.

**Caution:** Index usage stats reset when SQL Server restarts. A recently restarted server will show all indexes as unused. Check `last_user_seek` and `last_user_scan` before making any decisions.

#### Detecting Stale Statistics

`update_statistics.sql` finds statistics objects that have not been updated recently relative to the number of row changes:

```sql
SELECT
    OBJECT_NAME(s.object_id) AS TableName,
    s.name AS StatisticsName,
    sp.last_updated,
    sp.rows,
    sp.rows_sampled,
    sp.modification_counter,
    DATEDIFF(DAY, sp.last_updated, GETDATE()) AS DaysSinceUpdate
FROM sys.stats s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
    AND sp.modification_counter > 1000
ORDER BY sp.modification_counter DESC;
```

Stale statistics cause the query optimizer to generate execution plans based on outdated data distribution, leading to poor plan choices. If you see plan regressions after a large data load, stale statistics are often the cause.

---

### Step 3 — Contention

Blocking occurs when one session holds a lock that another session is waiting for. High `LCK_M_*` waits in your baseline point here.

Investigate with scripts from `sql-scripts/lock/`:

```sql
-- blocking_sessions_report.sql
SELECT
    blocking_session_id,
    session_id,
    wait_type,
    wait_time / 1000 AS wait_time_seconds,
    wait_resource,
    status
FROM sys.dm_exec_requests
WHERE blocking_session_id > 0;
```

Common resolutions:
- Add missing indexes to reduce lock duration (shorter queries hold locks for less time)
- Review transaction isolation levels (READ COMMITTED SNAPSHOT often helps OLTP workloads)
- Reduce transaction scope — commit early, lock late

---

### Step 4 — TempDB

High `PAGELATCH_UP` waits on allocation pages (`2:1:1`, `2:1:2`, `2:1:3`) indicate TempDB allocation contention. This happens when many sessions compete for the same allocation pages.

The fix is usually to add more TempDB data files — one per logical CPU core, up to 8:

```sql
-- Check current TempDB files
SELECT name, physical_name, size * 8 / 1024 AS size_mb
FROM tempdb.sys.database_files;
```

All TempDB files must be equal size and have identical autogrowth settings. Unequal files cause SQL Server to use the larger files disproportionately.

---

### Step 5 — Memory

Three metrics define memory health:

**Page Life Expectancy (PLE)** — how long a page stays in the buffer pool before being evicted. The old rule of thumb was > 300 seconds. For modern servers with large RAM, > 1000 seconds is more appropriate. A consistent decline in PLE means memory pressure.

**Buffer Cache Hit Ratio** — what percentage of page requests are served from memory. Should be > 95%.

**Memory Grants Pending** — queries waiting for a memory grant to execute their sort or hash operations. Should be 0 or very close to it during normal operations.

`RESOURCE_SEMAPHORE` waits in your baseline indicate queries are queuing for memory grants — a sign that `max server memory` may be too low or queries are requesting excessive memory.

---

### Step 6 — CPU

`SOS_SCHEDULER_YIELD` waits mean queries are running hot on CPU and voluntarily yielding their scheduler time slice. `CXPACKET` and `CXCONSUMER` waits indicate parallel query execution.

Parallelism is not always bad, but excessive parallelism can cause contention. The two key settings:

- **MAXDOP (Max Degree of Parallelism):** Controls how many CPUs a single query can use. A common starting point for OLTP workloads is MAXDOP = number of physical cores per NUMA node, up to 8.
- **Cost Threshold for Parallelism:** The estimated cost above which SQL Server considers a parallel plan. The default of 5 is too low for modern hardware — try 25–50 for OLTP workloads.

```sql
-- Review current settings
SELECT name, value_in_use
FROM sys.configurations
WHERE name IN ('max degree of parallelism', 'cost threshold for parallelism');
```

---

### Step 7 — I/O and Log

High `PAGEIOLATCH_SH` or `PAGEIOLATCH_EX` waits mean queries are waiting for data pages to be read from disk into the buffer pool. This is a data file I/O problem.

High `WRITELOG` waits mean the transaction log I/O cannot keep up with the write throughput.

Thresholds to measure:
- **Data files:** < 10ms is good, 10–20ms acceptable, > 20ms is poor
- **Log files:** < 5ms is good, 5–10ms acceptable, > 10ms is poor

```sql
-- Check file I/O latency
SELECT
    DB_NAME(vfs.database_id) AS DatabaseName,
    mf.physical_name,
    vfs.io_stall_read_ms / NULLIF(vfs.num_of_reads, 0) AS avg_read_latency_ms,
    vfs.io_stall_write_ms / NULLIF(vfs.num_of_writes, 0) AS avg_write_latency_ms
FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
INNER JOIN sys.master_files mf ON vfs.database_id = mf.database_id AND vfs.file_id = mf.file_id
ORDER BY avg_read_latency_ms DESC;
```

The best fix for I/O problems is missing indexes — fewer logical reads means fewer physical I/O requests. Hardware upgrades (SSD/NVMe) address the disk throughput ceiling.

---

### Step 8 — Config Review

Run through this checklist on a quarterly basis and after any major infrastructure change:

| Setting | Recommended | Why |
|---|---|---|
| `max server memory` | Total RAM minus OS overhead (~2–4 GB) | Prevents SQL Server from starving the OS |
| `max degree of parallelism` | Cores per NUMA node, max 8 | Controls parallel query cost |
| `cost threshold for parallelism` | 25–50 | Reduces unnecessary parallelism |
| `optimize for ad hoc workloads` | 1 (enabled) | Reduces plan cache bloat for OLTP |
| TempDB files | 1 per logical CPU, max 8, equal sizes | Eliminates allocation contention |
| Database autogrowth | Fixed MB increments, not % | Predictable and non-blocking growth |

---

### Step 9 — Verify

After every change, re-run your Step 1 baseline. Compare the wait statistics before and after. Log the comparison in the **Baseline_Log** tab of the workbook.

If the wait type you targeted went down — success. If a different wait type went up — you have a new problem to investigate. Either way, you have evidence and a paper trail.

**One change at a time. Always.**

---

## The Performance Workbook

The `performance_tuning_workbook.xlsx` is a companion to the SQL scripts. It has tabs for:

- **Methodology** — the 9-step workflow with guidance at each step
- **PerfMon_Counters** — the Windows Performance Monitor counters to collect alongside the SQL data (PLE, Batch Requests/sec, SQL Compilations/sec)
- **Index_Maintenance** — fragmentation thresholds and the rebuild vs. reorganize decision matrix
- **Config_Review** — the configuration checklist from Step 8
- **Baseline_Log** — a structured before/after tracking table

Open it before you start any tuning engagement. Log everything.

---

## Meet Your Agentic Performance Tuning Guide

Running the scripts is the easy part. Reading the output, understanding what the numbers mean, knowing which of the nine steps to jump to next — that is where most of the difficulty lies. The scripts tell you what is happening. Knowing what to do about it takes experience.

The `/performance` skill bridges that gap. It is a Claude skill that reads the actual scripts and their documentation files the moment you invoke it, maps your symptom to the right methodology step, and walks you through the analysis — from "I think something is slow" to "here is the exact query to run and here is what the results mean."

---

### Why Not Just Open the Script?

You could open `wait_statistics.sql`, run it in SSMS, and stare at the output. But that raises immediate questions:

- Which wait types are normal and which ones mean something?
- Is `CXPACKET` at 35% a problem or just background noise?
- Wait stats point to I/O pressure — so do I run `missing_indexes.sql` or `unused_indexes.sql` next?
- What threshold should PLE be at on a server with 256 GB of RAM?

The documentation files answer these questions — but you have to know to look there, find the right `.md` file, cross-reference it with the script output, and synthesize a recommendation. That chain of steps is what the skill collapses into a single conversation.

---

### A Real Scenario

It is Monday morning. Users are reporting that the application felt slow over the weekend. You do not know where to start.

```
/performance "queries slowed down after the weekend, high CPU"
```

The skill reads `wait_statistics.sql`, `missing_indexes.sql`, and their documentation files. It responds:

> **Step 6 — CPU Analysis**
>
> Your symptom (high CPU, post-weekend degradation) most often points to one of three causes: a plan regression after auto-statistics updates, increased parallelism contention, or missing indexes on a table that grew significantly over the weekend.
>
> Start here — run wait statistics to confirm the bottleneck category:
>
> ```sql
> SELECT TOP 20
>     wait_type,
>     wait_time_ms,
>     ROUND(100.0 * wait_time_ms / SUM(wait_time_ms) OVER (), 2) AS pct_total
> FROM sys.dm_os_wait_stats
> WHERE wait_type NOT IN (...)
> ORDER BY wait_time_ms DESC;
> ```
>
> **What to look for:**
> - High `SOS_SCHEDULER_YIELD` → queries are burning CPU cycles and yielding their scheduler time slice. This confirms CPU pressure. Next: look at your top CPU-consuming queries in Query Store.
> - High `CXPACKET` or `CXCONSUMER` → parallelism contention. Check MAXDOP and Cost Threshold for Parallelism settings.
> - High `LCK_M_*` → the slowness is actually blocking, not CPU. Re-route to Step 3.
>
> Want me to run this against your server? (yes/no)

You type `yes`. The skill runs the query via `sqlcmd`, gets the output, and continues:

> **Results show `SOS_SCHEDULER_YIELD` at 41% of total waits.**
>
> This confirms CPU pressure. The next step is finding which queries are consuming the most CPU. Run missing_indexes.sql — high CPU often correlates with queries doing full table scans instead of index seeks:
>
> *(presents missing_indexes.sql with explanation of the Avg_Estimated_Impact column and what score warrants creating an index)*

In ten minutes, you have gone from "something is slow" to a ranked list of index candidates with CREATE INDEX statements ready to review.

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
```

---

### How It Works Under the Hood

When you invoke `/performance`, Claude immediately runs:

```
Glob("performance/additional_queries/*.sql")
Glob("performance/additional_queries/docs/*.md")
```

It discovers all 4 scripts and their 4 documentation files, reads them all, and holds them in context for the conversation. It then maps your symptom against its internal routing table:

| Your words | Methodology step | Scripts loaded |
|---|---|---|
| slow queries, high CPU | Step 6 | `wait_statistics.sql` + `missing_indexes.sql` |
| blocking, deadlock, lock | Step 3 | `wait_statistics.sql` (LOCK wait types) |
| memory, PLE, buffer pool | Step 5 | `wait_statistics.sql` (RESOURCE_SEMAPHORE) |
| plan regression, statistics | any | `update_statistics.sql` |
| missing indexes | any | `missing_indexes.sql` |
| unused indexes, cleanup | any | `unused_indexes.sql` |
| step N | directly | script(s) for that step |

All performance scripts are **read-only diagnostics** — they query DMVs and system catalogs. They change nothing on your server. The skill can execute them via `sqlcmd` when you confirm, and it will interpret the output inline rather than leaving you to figure out what the numbers mean.

---

### What This Changes

Before the skill: you open `wait_statistics.sql`, run it, get output, open the documentation file, cross-reference wait type names, make a judgement call, open the next script, repeat.

After the skill: you describe what you are seeing in plain language. The skill reads the scripts and documentation, connects your symptom to the right step, presents the relevant query already explained, runs it if you want, and tells you what to look at in the output and what to do next.

The methodology does not change. The scripts do not change. What changes is how much cognitive overhead you carry between "something is slow" and "here is the problem and here is the fix."

---

*Data Eyes is an open-source SQL Server toolkit. The performance tuning toolkit covered in this article lives in the [performance/](https://github.com/lorenzouriel/data-eyes/tree/main/performance) folder of the repository.*
