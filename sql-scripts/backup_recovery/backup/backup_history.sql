/********************************************************************************************
 Script: SQL Server Backup History for a Specific Database
 Purpose: Retrieve last backup dates, backup type, and physical backup files.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- STEP 1: Check backup history for a specific database
-- Replace 'AdventureWorks2019' with your target database
SELECT 
    bs.database_name,                                  -- Database name
    MAX(bs.backup_finish_date) AS last_backup_finish, -- Date & time of the most recent backup
    bmf.physical_device_name,                          -- Physical backup file location
    bs.type AS backup_type,                            -- Backup type code (D=Full, I=Differential, L=Log)
    CASE bs.type
        WHEN 'D' THEN 'Full'
        WHEN 'I' THEN 'Differential'
        WHEN 'L' THEN 'Transaction Log'
        ELSE bs.type
    END AS backup_type_desc                             -- Friendly description of backup type
FROM msdb.dbo.backupset bs
LEFT JOIN msdb.dbo.backupmediafamily bmf 
    ON bs.media_set_id = bmf.media_set_id
WHERE [database_name] = 'AdventureWorks2019'          -- Target database filter
GROUP BY bs.database_name, bmf.physical_device_name, bs.type
ORDER BY bs.database_name, last_backup_finish DESC;  -- Most recent backups first
GO

/********************************************************************************************
 NOTES:
 - bs.type codes: 
     D = Full backup
     I = Differential backup
     L = Transaction Log backup
 - This query shows last backup times per backup type and physical file.
 - Useful for verifying backup schedules and ensuring compliance with RPO/RTO.
********************************************************************************************/