### Total Space per Table
```sql
SELECT 
    ISNULL(t.NAME, 'Total') AS TableName,
    ISNULL(s.NAME, '') AS SchemaName,
    CAST(ROUND(((SUM(a.total_pages) * 8) / 1024.0), 2) AS DECIMAL(18, 2)) AS TotalSpaceMB
FROM 
    sys.tables t
INNER JOIN      
    sys.indexes i ON t.OBJECT_ID = i.object_id
INNER JOIN 
    sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
INNER JOIN 
    sys.allocation_units a ON p.partition_id = a.container_id
INNER JOIN 
    sys.schemas s ON t.schema_id = s.schema_id
GROUP BY 
    ROLLUP(t.Name, s.Name)
ORDER BY 
    CASE WHEN t.Name IS NULL THEN 1 ELSE 0 END,
    TotalSpaceMB DESC;
```
* **Purpose:** To measure the total space allocated to each table in the database, including indexes and data.
* **Metric:** Total space per table in MB.
* **Use case:** Identifying large tables that may require optimization or monitoring storage usage.
* **Reference:** `sys.tables`, `sys.indexes`, `sys.partitions`, `sys.allocation_units`.

### Used Space per Table
```sql
SELECT 
    ISNULL(t.NAME, 'Total') AS TableName,
    ISNULL(s.NAME, '') AS SchemaName,
    CAST(ROUND(((SUM(a.used_pages) * 8) / 1024.0), 2) AS DECIMAL(18, 2)) AS UsedSpaceMB
FROM 
    sys.tables t
INNER JOIN      
    sys.indexes i ON t.OBJECT_ID = i.object_id
INNER JOIN 
    sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
INNER JOIN 
    sys.allocation_units a ON p.partition_id = a.container_id
INNER JOIN 
    sys.schemas s ON t.schema_id = s.schema_id
GROUP BY 
    ROLLUP(t.Name, s.Name)
ORDER BY 
    CASE WHEN t.Name IS NULL THEN 1 ELSE 0 END,
    UsedSpaceMB DESC;
```
* **Purpose:** To measure the actual used space of each table.
* **Metric:** Used space per table in MB.
* **Use case:** Tracking how much allocated storage is actually utilized.
* **Reference:** `sys.tables`, `sys.indexes`, `sys.partitions`, `sys.allocation_units`.

### Unused Space per Table
```sql
SELECT 
    ISNULL(t.NAME, 'Total') AS TableName,
    ISNULL(s.NAME, '') AS SchemaName,
    CAST(ROUND(((SUM(a.total_pages - a.used_pages) * 8) / 1024.0  * 100), 2) AS DECIMAL(18, 2)) AS UnusedSpaceMB
FROM 
    sys.tables t
INNER JOIN      
    sys.indexes i ON t.OBJECT_ID = i.object_id
INNER JOIN 
    sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
INNER JOIN 
    sys.allocation_units a ON p.partition_id = a.container_id
INNER JOIN 
    sys.schemas s ON t.schema_id = s.schema_id
GROUP BY 
    ROLLUP(t.Name, s.Name)
ORDER BY 
    CASE WHEN t.Name IS NULL THEN 1 ELSE 0 END,
    UnusedSpaceMB DESC;
```
* **Purpose:** To determine how much allocated space is unused per table.
* **Metric:** Unused space per table in MB (as percentage).
* **Use case:** Identifying tables with inefficient space usage for maintenance.
* **Reference:** `sys.tables`, `sys.indexes`, `sys.partitions`, `sys.allocation_units`.

### Pending Memory Grants
```sql
SELECT 
    COUNT(*) AS MemoryGrantsPending
FROM sys.dm_exec_query_memory_grants
WHERE grant_time IS NULL;
```
* **Purpose:** To track queries waiting for memory allocation.
* **Metric:** Count of pending memory grants.
* **Use case:** Monitoring memory pressure in SQL Server to detect performance bottlenecks.
* **Reference:** `sys.dm_exec_query_memory_grants`.

### Transaction Log Usage
```sql
dbcc sqlperf (logspace)
```
* **Purpose:** To report transaction log space usage per database.
* **Metric:** Log space used and percentage.
* **Use case:** Monitoring log growth and ensuring proper log backups.
* **Reference:** `DBCC SQLPERF`.

### Database Files Info
```sql
SELECT name AS FileName,
       size/128 AS FileSizeMB,
       physical_name AS PhysicalName
FROM sys.master_files;
```
* **Purpose:** To list database files and their sizes.
* **Metric:** File size in MB and physical file path.
* **Use case:** Tracking file sizes for storage management.
* **Reference:** `sys.master_files`.

### Active Locks
```sql
SELECT 
    request_session_id AS 'Session ID',
    resource_database_id AS 'Database ID',
    resource_associated_entity_id AS 'Entity ID',
    request_mode AS LockType,
    request_status AS Status
FROM sys.dm_tran_locks;
```
* **Purpose:** To monitor currently active locks in the database.
* **Metric:** Lock type, session, and status.
* **Use case:** Detecting blocking, deadlocks, or resource contention.
* **Reference:** `sys.dm_tran_locks`.

### Backup History
```sql
SELECT database_name, 
       backup_start_date, 
       backup_finish_date, 
       backup_size / 1024 / 1024 AS BackupSizeMB
FROM msdb.dbo.backupset
ORDER BY backup_start_date DESC;
```
* **Purpose:** To track database backup history and sizes.
* **Metric:** Backup start/finish date and size in MB.
* **Use case:** Verifying backup schedules and sizes.
* **Reference:** `msdb.dbo.backupset`.

### Row Counts per Table
```sql
SELECT 
    ISNULL(t.NAME, 'Total') AS TableName,
    ISNULL(s.NAME, '') AS SchemaName,
    SUM(p.rows) AS RowCounts
FROM 
    sys.tables t
INNER JOIN      
    sys.indexes i ON t.OBJECT_ID = i.object_id
INNER JOIN 
    sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
INNER JOIN 
    sys.schemas s ON t.schema_id = s.schema_id
GROUP BY 
    ROLLUP(t.Name, s.Name)
ORDER BY 
    CASE WHEN t.Name IS NULL THEN 1 ELSE 0 END,
    RowCounts DESC;
```
* **Purpose:** To count the number of rows per table.
* **Metric:** Row counts per table.
* **Use case:** Monitoring table growth trends and data distribution.
* **Reference:** `sys.tables`, `sys.partitions`.

### Memory Usage
```sql
SELECT 
    CAST(total_physical_memory_kb / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS Total_Physical_Memory_GB,
    CAST(available_physical_memory_kb / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS Available_Physical_Memory_GB,
    CAST(total_page_file_kb / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS Total_Page_File_GB,
    CAST(available_page_file_kb / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS Available_Page_File_GB
FROM sys.dm_os_sys_memory;
```
* **Purpose:** To monitor system memory usage on the server.
* **Metric:** Total and available physical memory and page file in KB or GB.
* **Use case:** Detecting memory pressure affecting SQL Server performance.
* **Reference:** `sys.dm_os_sys_memory`.

### Disk I/O Stats per Database File
```sql
SELECT database_id, 
       file_id, 
       io_stall_read_ms AS DiskReadStall, 
       io_stall_write_ms AS DiskWriteStall, 
       num_of_reads, 
       num_of_writes
FROM sys.dm_io_virtual_file_stats (2, NULL);
```
* **Purpose:** To monitor disk I/O performance per database file.
* **Metric:** Read/write stalls and counts per file.
* **Use case:** Identifying I/O bottlenecks and slow storage.
* **Reference:** `sys.dm_io_virtual_file_stats`.

### Database size per database
```sql
SELECT 
    db.name AS DatabaseName,
    mf.name AS FileName,
    mf.type_desc AS FileType,
    CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(10,2)) AS FileSize_GB,
    CAST((mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024 / 1024 AS DECIMAL(10,2)) AS FreeSpace_GB,
    vs.total_bytes / 1024.0 / 1024 / 1024 AS DriveSize_GB,
    vs.available_bytes / 1024.0 / 1024 / 1024 AS DriveFreeSpace_GB
FROM sys.master_files mf
INNER JOIN sys.databases db ON db.database_id = mf.database_id
CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
ORDER BY db.name, mf.type_desc;

-- Sum of values
SELECT 
    SUM(CAST(mf.size * 8.0 / 1024 / 1024 AS DECIMAL(10,2))) AS FileSize_GB,
    SUM(CAST((mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024 / 1024 AS DECIMAL(10,2))) AS FreeSpace_GB,
    vs.total_bytes / 1024.0 / 1024 / 1024 AS DriveSize_GB,
    vs.available_bytes / 1024.0 / 1024 / 1024 AS DriveFreeSpace_GB
FROM sys.master_files mf
INNER JOIN sys.databases db ON db.database_id = mf.database_id
CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
GROUP BY vs.total_bytes, vs.available_bytes
```
* **Purpose:** Provide a snapshot of database file sizes and free space on disk for all databases. Helps monitor storage utilization and prevent space-related issues.
* **Metric:** 
    * DatabaseName → Name of the database.
    * FileName → Logical file name.
    * FileType → Type of file: ROWS (data) or LOG (transaction log).
    * FileSize_GB → Total size of the file in GB.
    * FreeSpace_GB → Available free space inside the file in GB.
    * DriveSize_GB → Total size of the drive hosting the file.
    * DriveFreeSpace_GB → Free space available on the drive.
* **Use case:** 
    * Detect databases approaching their file size limit.
    * Monitor log and data file growth.
    * Identify low disk space on drives hosting databases to prevent failures.
    * Useful for capacity planning and maintenance.
* **Reference:** 
    * sys.master_files → SQL Server system view for database files.
    * FILEPROPERTY() → Returns file space usage info.
    * sys.dm_os_volume_stats() → Provides disk-level statistics for database files.