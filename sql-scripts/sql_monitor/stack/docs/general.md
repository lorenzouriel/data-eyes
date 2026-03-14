### Database Name
```sql
SELECT DB_NAME() AS DatabaseName;
```

* **Purpose:** Identify the **current database context** you are connected to.
* **Metric:**
  * `DatabaseName` → The name of the database where the query is executed.
* **Use case:**
  * Useful in scripts that are run across multiple databases or in automated reports to tag results by database.

### SQL Server Start Time
```sql
SELECT 
	sqlserver_start_time AS 'SQL SERVER START TIME'
FROM sys.dm_os_sys_info;
```

* **Purpose:** Determine **how long the SQL Server instance has been running**.
* **Metric:**
  * `SQL SERVER START TIME` → Date and time the SQL Server service started.
* **Use case:**
  * Monitor **uptime** for maintenance windows, restarts, and troubleshooting.
  * Helps correlate performance issues with recent restarts or patches.

### Active User Sessions
```sql
SELECT 
	login_name AS LoginName,
    COUNT(session_id) AS SessionCount
FROM sys.dm_exec_sessions
WHERE is_user_process = 1
GROUP BY login_name
ORDER BY SessionCount DESC;
```
* **Purpose:** Identify the **number of active sessions per user login**.
* **Metrics:**
  * `LoginName` → SQL Server login name of active user sessions.
  * `SessionCount` → Number of active sessions for each login.
* **Use case:**
  * Detect **high activity users** or potential runaway processes.
  * Monitor **concurrent connections** and plan for resource usage.
  * Useful in performance dashboards or when investigating blocking/locking issues.