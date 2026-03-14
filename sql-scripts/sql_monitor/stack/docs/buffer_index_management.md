### Buffer Pool Usage & Dirty Pages
```sql
SELECT 
    CAST(COUNT(*) * 8.0 / 1024 AS DECIMAL(10, 2)) AS 'Buffer Pool Used MB',
    CAST(SUM(CASE WHEN is_modified = 1 THEN 1 ELSE 0 END) * 8.0 / 1024 AS DECIMAL(10, 2)) AS 'Dirty Buffer MB',
    CAST(COUNT(*) * 8.0 / 1024 AS DECIMAL(10, 2)) AS 'Buffer Pool Total MB',
    CAST(SUM(CASE WHEN is_modified = 1 THEN 1 ELSE 0 END) * 8.0 / 1024 AS DECIMAL(10, 2)) AS 'Dirty Buffer Used MB'
FROM sys.dm_os_buffer_descriptors
WHERE database_id > 4;
```
* **Purpose:** Monitor **buffer pool usage** and **dirty pages** (pages modified but not yet written to disk).
* **Metrics:**
  * `Buffer Pool Used MB` → Total memory used by the buffer pool for user databases.
  * `Dirty Buffer MB` → Memory occupied by pages pending flush to disk.
  * `Buffer Pool Total MB` → Total buffer pool memory allocated.
  * `Dirty Buffer Used MB` → Redundant with dirty buffer, useful for alerting.
* **Use case:** Identify **memory pressure** and potential I/O bottlenecks.
  * High dirty pages → heavy write activity.
  * Helps identify I/O flush bottlenecks.
  * See how much buffer pool memory is used by user databases.
  * Helps decide if more memory is needed for SQL Server.

### System Memory Status
```sql
SELECT 
    (total_physical_memory_kb / 1024) AS 'Total Physical Memory MB',
    (available_physical_memory_kb / 1024) AS 'Available Physical Memory MB',
    (total_page_file_kb / 1024) AS 'Total Page File MB',
    (available_page_file_kb / 1024) AS 'Available Page File MB',
    (system_memory_state_desc) AS 'System Memory State Description'
FROM sys.dm_os_sys_memory;
```
* **Purpose:** Monitor **physical and virtual memory availability** for SQL Server and the OS.
* **Metrics:**
  * `Total Physical Memory MB` → Installed RAM.
  * `Available Physical Memory MB` → Free RAM available.
  * `Total Page File MB` → Virtual memory size.
  * `Available Page File MB` → Free virtual memory.
  * `System Memory State Description` → Overall memory pressure indicator.
* **Use case:** Detect **low memory conditions** and prevent **slowdowns or memory throttling**.
  * Ensure enough free RAM is available for SQL Server buffer pool, queries, and tempdb.
  * Low Available Physical Memory or Available Page File → high memory usage by SQL Server or other processes.
  * Compare Total Physical Memory vs. SQL Server memory allocation to check if the server has enough memory for expected workload.

### Index Usage Statistics
```sql
SELECT 
    OBJECT_NAME(s.object_id) AS TableName,
    i.name AS IndexName,
    s.user_seeks,
    s.user_scans,
    s.user_lookups,
    s.user_updates
FROM sys.dm_db_index_usage_stats AS s
INNER JOIN sys.indexes AS i ON i.object_id = s.object_id AND i.index_id = s.index_id
WHERE s.database_id = DB_ID(DB_NAME())
ORDER BY s.user_seeks DESC;
```
* **Purpose:** Analyze **how indexes are being used** (reads and writes).
* **Metrics:**
  * `user_seeks` → Number of seeks (efficient index usage).
  * `user_scans` → Number of table/index scans.
  * `user_lookups` → Lookups using included columns.
  * `user_updates` → Updates applied to index.
* **Use case:** Detect **unused indexes** (low `user_seeks`) or **heavily updated indexes**, informing **index maintenance strategy**.
  * Indexes with user_seeks = 0, user_scans = 0, and low user_lookups may not be needed.
  * High user_seeks → frequently queried, critical for query performance.
  * High user_updates → index maintenance may affect insert/update/delete performance.
  * Decide which indexes to keep, remove, or consolidate. Helps optimize storage, reduce fragmentation, and improve query performance.

### Page Life Expectancy (PLE)
```sql
SELECT [object_name], [counter_name], [cntr_value] AS PageLifeExpectancy
FROM sys.dm_os_performance_counters
WHERE [object_name] LIKE '%Buffer Manager%'
AND [counter_name] = 'Page life expectancy';
```
* **Purpose:** Measure **how long pages stay in memory** before being flushed to disk.
* **Metric:** `PageLifeExpectancy` → Higher is better (longer caching of pages).
* **Use case:** Low PLE indicates **memory pressure** or **high I/O**.
* **Reference:** Recommended baseline ≥ 300 seconds; < 300 may indicate **memory bottlenecks**.