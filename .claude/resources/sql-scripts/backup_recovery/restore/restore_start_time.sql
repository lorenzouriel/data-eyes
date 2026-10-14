/********************************************************************************************
 Script: SQL Server Restore History and Backup Performance Check
 Purpose: Review restore history, backup durations, sizes, and check error logs.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- STEP 1: List restore history and related backup details
-- Includes: database restored, restore date, backup start & finish, duration, size
SELECT 
    r.destination_database_name,                         -- Database that was restored
    r.restore_date AS restore_completed_at,             -- When restore completed
    b.backup_start_date,                                -- Backup start time
    b.backup_finish_date,                               -- Backup finish time
    DATEDIFF(SECOND, b.backup_start_date, b.backup_finish_date) AS backup_duration_seconds, -- Duration in seconds
    b.backup_size / 1024 / 1024 AS backup_size_MB       -- Backup size in MB
FROM msdb.dbo.restorehistory r
JOIN msdb.dbo.backupset b ON r.backup_set_id = b.backup_set_id
ORDER BY r.restore_date DESC;                          -- Most recent restores first
GO

-- STEP 2: Check SQL Server error log for Restore operations
-- This helps review restore performance or errors (MB/sec, issues during restore)
EXEC sp_readerrorlog 0, 1, N'Restore';
GO

-- STEP 3: Search SQL Server error log for a specific database
EXEC xp_readerrorlog 0, 1, N'AdventureWorks2019';
GO

/********************************************************************************************
 NOTES:
 - Use these queries to monitor restore history, backup durations, and performance.
 - DATEDIFF gives duration in seconds; backup_size is converted to MB.
 - sp_readerrorlog and xp_readerrorlog allow filtering for specific keywords like 'Restore' or a database name.
 - Always run with appropriate permissions (sysadmin or db_backupoperator recommended).
********************************************************************************************/