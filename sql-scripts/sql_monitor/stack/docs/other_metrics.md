### Database Availability
```sql
SELECT 
    d.name AS [Database],
    d.state_desc AS [Status],
    CAST(100.0 * (1 - (rs.[cntr_value] / DATEDIFF(SECOND, sqlserver_start_time, GETDATE()))) AS DECIMAL(5,2)) AS [AvailabilityPercent]
FROM sys.databases d
CROSS JOIN sys.dm_os_sys_info si
CROSS APPLY (
    SELECT [cntr_value]
    FROM sys.dm_os_performance_counters
    WHERE counter_name = 'Log Flush Waits/sec'
) rs
CROSS APPLY (
    SELECT sqlserver_start_time FROM sys.dm_os_sys_info
) st;
```
**Purpose:** Measure the **approximate percentage of time each database has been online** since the last SQL Server restart.
**Use Case:** Track **uptime and availability trends** to ensure SLAs are met.
**Benefits:** Provides a **quick health indicator** for all databases; helps identify **unexpected restarts or downtime**.
*Note:* For precise SLA tracking, use **SQL Server Agent monitoring** or external tools like **SCOM/Zabbix**.

### Database Connections
```sql
SELECT 
    DB_NAME(dbid) AS [Database],
    COUNT(*) AS [TotalConnections],
    SUM(CASE WHEN status = 'sleeping' THEN 1 ELSE 0 END) AS [Idle],
    SUM(CASE WHEN status <> 'sleeping' THEN 1 ELSE 0 END) AS [Active]
FROM sys.sysprocesses
WHERE dbid > 0
GROUP BY dbid;
```
**Purpose:** Count the **number of connections per database**, broken down by idle and active sessions.
**Use Case:** Detect **connection spikes, potential blocking, or over-utilization**.
**Benefits:** Helps **capacity planning**, **load analysis**, and **detecting abandoned sessions** that may impact performance.

### Query Performance – Average Execution Time
```sql
SELECT TOP 10
    DB_NAME(st.dbid) AS [Database],
    qs.execution_count,
    qs.total_elapsed_time / qs.execution_count AS [Avg_Elapsed_Time_ms],
    qs.total_worker_time / qs.execution_count AS [Avg_CPU_Time_ms],
    qs.max_elapsed_time AS [Max_Elapsed_Time_ms],
    SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
        ((CASE qs.statement_end_offset
            WHEN -1 THEN DATALENGTH(st.text)
            ELSE qs.statement_end_offset END
            - qs.statement_start_offset)/2)+1) AS [QueryText]
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
ORDER BY [Avg_Elapsed_Time_ms] DESC;
```
**Purpose:** Identify the **top 10 queries by average execution time**.
**Use Case:** Detect **long-running queries** that may be impacting performance.
**Benefits:** Enables **query optimization**, **index tuning**, and **CPU resource management**.

### Slow Query Alerts (> 30s)
```sql
SELECT 
    DB_NAME(st.dbid) AS [Database],
    qs.execution_count,
    qs.max_elapsed_time AS [Max_Elapsed_Time_ms],
    SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
        ((CASE qs.statement_end_offset
            WHEN -1 THEN DATALENGTH(st.text)
            ELSE qs.statement_end_offset END
            - qs.statement_start_offset)/2)+1) AS [QueryText]
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
WHERE qs.max_elapsed_time > 30000 -- greater than 30 seconds
ORDER BY qs.max_elapsed_time DESC;
```
**Purpose:** Identify queries that **exceed 30 seconds execution time**.
**Use Case:** Alert DBA team to **potential performance issues or blocking queries**.
**Benefits:** Improves **response time**, reduces **user impact**, and guides **query tuning efforts**.

### Last Backup Taken
```sql
SELECT 
    d.name AS [Database],
    MAX(b.backup_finish_date) AS [LastBackup],
    b.type AS [BackupType]
FROM msdb.dbo.backupset b
JOIN sys.databases d ON b.database_name = d.name
GROUP BY d.name, b.type
ORDER BY [LastBackup] DESC;
```
**Purpose:** Track the **most recent backup for each database**.
**Use Case:** Verify **backup compliance** with RTO/RPO requirements.
**Benefits:** Reduces **risk of data loss** and ensures **recovery readiness**.

### Backup Type (FULL, DIFFERENTIAL, LOG)
```sql
SELECT 
    d.name AS [Database],
    CASE b.type
        WHEN 'D' THEN 'FULL'
        WHEN 'I' THEN 'DIFFERENTIAL'
        WHEN 'L' THEN 'LOG'
        ELSE 'OTHER'
    END AS [BackupType],
    MAX(b.backup_finish_date) AS [LastBackup]
FROM msdb.dbo.backupset b
JOIN sys.databases d ON b.database_name = d.name
GROUP BY d.name, b.type
ORDER BY [LastBackup] DESC;
```
**Purpose:** Determine **the type of backup** most recently performed for each database.
**Use Case:** Ensure **backup strategy is consistent** (FULL + DIFF + LOG).
**Benefits:** Supports **audit compliance**, **RPO adherence**, and **disaster recovery planning**.