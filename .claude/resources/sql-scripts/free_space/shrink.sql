/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Shrink database and log files in SQL Server
-- Description:  Demonstrates database-level and file-level shrink operations
-- Notes:        Shrinking files frequently is not recommended as it can cause fragmentation.
--               Use carefully, preferably during low activity periods.
************************************************************************************************/

-- ============================================================
-- 1. Shrink the entire database
-- ============================================================
/*
Shrinks the data and log files of the specified database.
The second parameter (10) is the target percentage of free space to leave after the shrink.
*/
DBCC SHRINKDATABASE (my_database, 10);  
GO

-- ============================================================
-- 2. Check database files and their physical paths
-- ============================================================
/*
Lists logical and physical names of files for a database, including type (ROWS/LOG).
Useful to identify which files to shrink or monitor.
*/
SELECT 
    name AS [Logical_Name],          -- Logical file name used in SQL
    physical_name AS [Physical_Name],-- OS-level path of the file
    type_desc AS [File_Type]         -- ROWS = data file, LOG = transaction log
FROM sys.master_files
WHERE database_id = DB_ID(N'SSISDB'); -- Replace with your database
GO

-- ============================================================
-- 3. Shrink a specific log file
-- ============================================================
/*
Shrinks a specific file (usually a log file).
The second parameter (10) is the target size in MB or target percent depending on SQL Server version.
Make sure to backup logs before shrinking to avoid data loss.
*/
DBCC SHRINKFILE (log, 10);  
GO
