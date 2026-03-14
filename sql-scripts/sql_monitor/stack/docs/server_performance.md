### Top 10 Longest Running Queries
```sql
SELECT TOP 10
       creation_time AS CreationTime,
       total_elapsed_time/1000 AS TotalElapsedTimeMS,
       execution_count AS ExecutionCount,
       total_worker_time/1000 AS CPUTimeMS
FROM sys.dm_exec_query_stats
ORDER BY total_elapsed_time DESC;
```
* **Purpose:** Identify queries consuming the **most total execution time**.
* **Metrics:**
  * `TotalElapsedTimeMS` → Total elapsed time (ms).
  * `ExecutionCount` → Number of times executed.
  * `CPUTimeMS` → CPU time used by the query (ms).
  * `CreationTime` → When the plan was compiled.
* **Use case:** Detect high-impact queries for **performance tuning**.

### Currently Running Threads
```sql
SELECT 
  COUNT(*) AS Running_Threads
FROM sys.dm_exec_requests
WHERE status = 'running';
```
* **Purpose:** Count active threads currently executing queries.
* **Metric:** `Running_Threads` → Number of concurrent executing requests.
* **Use case:** Monitor **concurrent activity**, detect **thread storms** or query blocking.
  * High number of running threads may indicate CPU pressure or inefficient queries.
  * Helps see how many queries are concurrently executing.

### Pending I/O Requests
```sql
SELECT 
    COUNT(*) AS OpenFiles
FROM sys.dm_io_pending_io_requests;
```
* **Purpose:** Identify **I/O operations waiting to complete**.
* **Metric:** `OpenFiles` → Number of pending I/O requests.
* **Use case:** Detect potential **disk bottlenecks** affecting performance.
  * Pending I/O indicates how many disk operations are waiting, which may reflect slow storage, high concurrency, or large queries.
  * A high number of pending I/O requests can point to disk performance issues, I/O saturation, or queries scanning large amounts of data.

### Active Locks
```sql
SELECT 
    request_session_id AS SessionID,
    resource_database_id AS DatabaseID,
    resource_associated_entity_id AS EntityID,
    request_mode AS LockType,
    request_status AS Status
FROM sys.dm_tran_locks;
```
* **Purpose:** Track **active locks** held or requested in the system.
* **Metrics:**
  * `SessionID` → ID of session holding/requesting the lock.
  * `DatabaseID` → Database containing the locked resource.
  * `EntityID` → Object or page ID.
  * `LockType` → Lock mode (e.g., `X`, `S`).
  * `Status` → Granted or waiting.
* **Use case:** Troubleshoot **blocking, deadlocks, or contention**.
  * Check which sessions are waiting on locks (Status = 'WAIT').
  * Identify conflicting locks and involved sessions.
  * Detect hot spots in tables or indexes where locks are heavily requested.

### Session Space Usage
```sql
SELECT 
    SUM(user_objects_alloc_page_count) AS 'User Object Pages',
    SUM(internal_objects_alloc_page_count) AS 'Internal Object Pages'
FROM sys.dm_db_session_space_usage;
```
* **Purpose:** Monitor **memory/pages allocated by current sessions**.
* **Metrics:**
  * `User Object Pages` → Pages used by user objects (tables, indexes).
  * `Internal Object Pages` → Pages used by internal SQL Server structures.
* **Use case:** Detect **memory pressure** caused by session activity.
  * Track how much session memory is allocated for user and internal objects.
  * High internal_objects_alloc_page_count → may indicate large sorts, joins, or hash operations consuming tempdb memory.
  * Can identify queries that generate heavy tempdb usage via internal objects.

### Active Transactions
```sql
SELECT 
	  transaction_id AS TransactionID,
    transaction_begin_time AS BeginTime,
    transaction_state AS State,
    transaction_type AS Type
FROM sys.dm_tran_active_transactions;
```
* **Purpose:** Track **transactions currently open** in SQL Server.
* **Metrics:**
  * `TransactionID` → Unique transaction identifier.
  * `BeginTime` → When transaction started.
  * `State` → Active, committing, or rolling back.
  * `Type` → Transaction type (read/write).
* **Use case:** Detect **long-running or uncommitted transactions**.
  * Spot transactions that have been open for too long.
  * Long-running transactions can hold locks and block other queries.
  * Open transactions prevent log truncation, potentially causing log growth.

### Wait Statistics (excluding idle waits)
```sql
SELECT 
	   wait_type, 
     SUM(wait_time_ms) AS WaitTimeMS, 
     SUM(waiting_tasks_count) AS TaskCount
FROM sys.dm_os_wait_stats
WHERE wait_type NOT IN ('SLEEP_TASK', 'BROKER_TASK_STOP', 'SQLTRACE_BUFFER_FLUSH')
GROUP BY wait_type
ORDER BY WaitTimeMS DESC;
```
* **Purpose:** Identify where SQL Server **spends time waiting**, excluding trivial or idle waits.
* **Metrics:**
  * `WaitTimeMS` → Total wait time in milliseconds.
  * `TaskCount` → Number of waiting tasks.
  * `wait_type` → Type of wait (e.g., `PAGEIOLATCH_SH`, `LCK_M_X`).
* **Use case:** Troubleshoot **performance bottlenecks** caused by I/O, locks, or memory.
  * Example: PAGEIOLATCH_SH → waiting on data pages from disk.
  * Example: LCK_M_X → waiting for exclusive locks.
  * Example: SOS_SCHEDULER_YIELD → waiting for CPU.
  * High wait time → investigate queries, indexes, or hardware.