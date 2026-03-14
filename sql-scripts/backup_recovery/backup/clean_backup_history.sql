/********************************************************************************************
 Script: Cleanup Old Backup History
 Purpose: Remove old backup and restore history entries from MSDB to keep system tables manageable.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- STEP 0: Prevent extra result sets from interfering with scripts
SET NOCOUNT ON;
GO

-- STEP 1: Declare a variable to define the cutoff date
DECLARE 
    @CleanupDate DATETIME;

-- STEP 2: Set cutoff date to 30 days ago from today
SET @CleanupDate = DATEADD(DAY, -30, GETDATE());

-- STEP 3: Execute system stored procedure to delete old backup history
-- Removes backup and restore history older than @CleanupDate
EXECUTE dbo.sp_delete_backuphistory @oldest_date = @CleanupDate;
GO

/********************************************************************************************
 NOTES:
 - sp_delete_backuphistory removes entries from MSDB tables: backupset, backupfile, backupmediafamily, restorehistory, etc.
 - Adjust the number of days (here 30) according to your retention policy.
 - Regular cleanup helps maintain performance of MSDB and prevents unnecessary growth.
 - This does NOT delete actual backup files on disk.
********************************************************************************************/