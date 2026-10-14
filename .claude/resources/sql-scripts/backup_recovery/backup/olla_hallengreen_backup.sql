/********************************************************************************************
 Script: Database Backup and Azure Blob Upload
 Purpose: Perform FULL, Differential, and Transaction Log backups with compression, verification,
          automatic cleanup, and upload to Azure Blob Storage.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-------------------------
-- STEP 1: FULL Backup
-------------------------
EXECUTE dbo.DatabaseBackup 
    @Databases = 'database_name',   -- Database to backup
    @Directory = 'G:\Backup',       -- Local backup directory
    @BackupType = 'FULL',           -- Full backup
    @Compress = 'Y',                -- Enable compression
    @Verify = 'Y',                  -- Verify backup integrity
    @CleanupTime = 720,             -- Cleanup backups older than 720 hours (30 days)
    @CleanupMode = 'AFTER_BACKUP';  -- Cleanup mode
GO

-- STEP 1b: Upload FULL backup to Azure Blob Storage
-- Using AzCopy command-line tool
-- Adjust the container URL and SAS token as needed
-- Limit upload bandwidth to 100 Mbps
!c:\tools\azcopy\azcopy.exe copy "G:\Backup\FULL" "https://<storageaccount>.blob.core.windows.net/bonicio-database_name-backups?" ^
--overwrite=false --include-pattern=*.bak --include-path="database_name\FULL" --recursive --cap-mbps 100

-------------------------
-- STEP 2: Differential Backup
-------------------------
EXECUTE dbo.DatabaseBackup 
    @Databases = 'database_name',
    @Directory = 'G:\Backup',
    @BackupType = 'DIFF',           -- Differential backup
    @Compress = 'Y',
    @Verify = 'Y',
    @CleanupTime = 720,
    @CleanupMode = 'AFTER_BACKUP';
GO

-- STEP 2b: Upload DIFF backup to Azure Blob Storage
!c:\tools\azcopy\azcopy.exe copy "G:\Backup\DIFF" "https://<storageaccount>.blob.core.windows.net/bonicio-database_name-backups?" ^
--overwrite=false --include-pattern=*.bak --include-path="database_name\DIFF" --recursive --cap-mbps 100

-------------------------
-- STEP 3: Transaction Log Backup
-------------------------
EXECUTE dbo.DatabaseBackup 
    @Databases = 'database_name',
    @Directory = 'G:\Backup',
    @BackupType = 'LOG',            -- Transaction log backup
    @Compress = 'Y',
    @Verify = 'Y',
    @CleanupTime = 720,
    @CleanupMode = 'AFTER_BACKUP';
GO

-- STEP 3b: Upload LOG backup to Azure Blob Storage
!c:\tools\azcopy\azcopy.exe copy "G:\Backup\LOG" "https://<storageaccount>.blob.core.windows.net/bonicio-database_name-backups?" ^
--overwrite=false --include-pattern=*.bak --include-path="database_name\LOG" --recursive --cap-mbps 100

/********************************************************************************************
 NOTES:
 - dbo.DatabaseBackup is assumed to be Ola Hallengren’s maintenance solution stored procedure.
 - Compression reduces backup size; verify ensures backup integrity.
 - CleanupTime = 720 hours = 30 days; older backups will be removed automatically.
 - AzCopy is used to copy backups to Azure Blob Storage; adjust SAS token, container URL, and bandwidth cap.
 - The --overwrite=false option prevents overwriting existing files on Azure.
********************************************************************************************/