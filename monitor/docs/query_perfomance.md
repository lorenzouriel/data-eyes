### Top 10 Longest Running Queries
```sql
SELECT TOP 10
    qs.total_elapsed_time / qs.execution_count / 1000.0 AS avg_duration_ms,
    qs.execution_count,
    SUBSTRING(qt.text, qs.statement_start_offset/2,
              (CASE
                  WHEN qs.statement_end_offset = -1 THEN LEN(CONVERT(NVARCHAR(MAX), qt.text)) * 2
                  ELSE qs.statement_end_offset
               END - qs.statement_start_offset)/2) AS query_text
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
ORDER BY avg_duration_ms DESC;
```

* **Purpose:** Identify queries that take the **longest average execution time**.
* **Metrics:**
  * `avg_duration_ms` → Average execution time per execution (ms).
  * `execution_count` → How many times the query has run.
  * `query_text` → SQL statement text.
* **Use case:** Detect **slow-performing queries** for tuning or indexing.

### Ad-Hoc Query Cache Hit Ratio
```sql
SELECT 
    (CAST(SUM(CASE WHEN usecounts > 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) * 100 AS Cache_Hit_Ratio
FROM sys.dm_exec_cached_plans
WHERE objtype = 'Adhoc'
    OR objtype = 'Prepared';
```
* **Purpose:** Measure **how effectively the plan cache is reused**.
* **Metric:**
  * `Cache_Hit_Ratio` → Percentage of cached plans that are reused.
* **Use case:** Identify potential **query plan churn**; low hit ratio → consider parameterizing queries.
  * **High ratio (90–100%)** → SQL Server is reusing plans efficiently, low plan churn.
  * **Low ratio (<50%)** → Many plans are cached but not reused, which may indicate:
    * Excessive ad-hoc queries
    * Lack of parameterization
    * Plan cache bloat

### Wait Statistics
```sql
DBCC SQLPERF (WAITSTATS);
```
* **Purpose:** Analyze **where SQL Server is spending time waiting**.
* **Metric:** Wait types and cumulative wait time.
* **Use case:** Detect **bottlenecks** like I/O, locking, or CPU waits for performance tuning.

### Active Connections Count
```sql
SELECT 
  COUNT(session_id) AS Connections
FROM sys.dm_exec_sessions
WHERE is_user_process = 1;
```
* **Purpose:** Monitor **number of active user connections**.
* **Metric:**
  * `Connections` → Total active user sessions.
* **Use case:** Capacity planning, detecting **connection storms**, or performance troubleshooting.

### Low-Use Cache Plans
```sql
SELECT 
	plan_handle,
	cacheobjtype AS CacheObjectType,
    objtype AS ObjectType,
    usecounts AS 'Use Count',
    size_in_bytes AS 'Cache Size'
FROM sys.dm_exec_cached_plans
WHERE usecounts < 10;
```
* **Purpose:** Identify **cached plans that are rarely reused**.
* **Metrics:**
  * `CacheObjectType`, `ObjectType` → Type of cache object.
  * `Use Count` → Number of times plan was executed.
  * `Cache Size` → Memory consumed.
* **Use case:** Detect **plan cache pollution**, which can reduce efficiency and identify low-use cached plans that may be occupying memory but not being reused.
  * These plans contribute to plan cache pollution, where memory is taken up by unnecessary or one-off ad-hoc plans.
  * To clean a low-use, run:: `DBCC FREEPROCCACHE (0x0...);`

### Top 10 Queries by Logical Reads
```sql
SELECT TOP 10
       creation_time AS CreationTime,
       total_logical_reads AS LogicalReads
FROM sys.dm_exec_query_stats
ORDER BY total_elapsed_time DESC;
```
* **Purpose:** Find queries **consuming the most logical reads** (I/O impact).
* **Metrics:**
  * `CreationTime` → When query plan was created.
  * `LogicalReads` → Number of logical reads performed.
* **Use case:** Identify **high I/O queries** for indexing or tuning.

### Top 10 CPU-Intensive Queries
```sql
SELECT TOP 10
       st.text AS QueryText,
       qs.total_worker_time AS CPUTime,
       qs.total_elapsed_time AS TotalTime,
       qs.total_logical_reads AS LogicalReads
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY qs.total_worker_time DESC;
```
* **Purpose:** Identify **queries consuming the most CPU**.
* **Metrics:**
  * `CPUTime` → Total CPU time used (microseconds).
  * `TotalTime` → Total elapsed time.
  * `LogicalReads` → Total logical reads.
  * `QueryText` → SQL statement.
* **Use case:** Optimize **CPU-heavy queries** or troubleshoot high CPU spikes.
