/********************************************************************************************
 Script: Determine Latest Differential Backup for FTP Transfer
 Purpose: Retrieve the most recent differential backup file and construct the remote FTP path.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- STEP 0: Declare variables
DECLARE 
    @FTPPath varchar(1024) = '/backup/DIFF/',  -- Remote FTP folder path where backups will be stored
    @BakName  varchar(1024),                   -- Backup file name (to be extracted)
    @RemoteFolderPath varchar(1024);           -- Full remote path including file name

-- STEP 1: Get the most recent differential backup file
-- 'I' type indicates a differential backup (D = Full, L = Log)
SELECT TOP 1 
    --physical_device_name, -- original full path (commented out)
    @BakName = SUBSTRING(
        physical_device_name, 
        LEN(physical_device_name) - CHARINDEX('\', REVERSE(physical_device_name)) + 2, 
        LEN(physical_device_name)
    )
FROM msdb.dbo.backupmediafamily
WHERE media_set_id = (
    SELECT TOP 1 media_set_id
    FROM msdb.dbo.backupset
    WHERE type = 'I' -- Differential backup
    ORDER BY backup_finish_date DESC
);

-- STEP 2: Construct the full remote FTP path
SET @RemoteFolderPath = @FTPPath + @BakName;

-- STEP 3: Display the results
SELECT 
    @RemoteFolderPath AS [RemoteFolderPath],  -- Full remote path including file name
    @BakName AS [BackupName];                 -- Backup file name only
GO

/********************************************************************************************
 NOTES:
 - This script retrieves the latest differential backup file for a database.
 - The backup type 'I' corresponds to differential backups.
 - SUBSTRING with REVERSE extracts the file name from the full local path.
 - @RemoteFolderPath can be used in FTP scripts or automation tasks for uploading backups.
********************************************************************************************/