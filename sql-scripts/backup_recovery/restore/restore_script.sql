/********************************************************************************************
 Script: Restore SQL Server Database from Full Backup
 Purpose: Restore the database from a full backup file.
********************************************************************************************/

-- =Restore the database from the first full backup
-- Replace the file path with the actual location of your backup.
USE [master];  -- Always use master when performing restores
GO

RESTORE DATABASE [database_name]  -- Replace with your database name
FROM DISK = N'C:\Backup\FULL\database.bak'  -- Path to the backup file
WITH 
    FILE = 1,          -- Specifies which backup set to restore from (first in this case)
    NOUNLOAD,          -- Keeps the media loaded after restore (default for disk backups)
    STATS = 5;         -- Shows progress in percentage
GO