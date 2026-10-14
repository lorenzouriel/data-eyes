/********************************************************************************************
 Script: Switching Database to FULL Recovery Model
 Purpose: Configure database for point-in-time recovery and prevent uncontrolled log growth.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- STEP 1: Switch to FULL Recovery Model
-- This enables point-in-time recovery. However, it won’t be active until a full backup is taken.
ALTER DATABASE [YourDatabaseName] SET RECOVERY FULL;
GO

-- STEP 2: Take a FULL BACKUP immediately
-- This full backup is required to "activate" the FULL recovery model.
-- Without this backup, transaction log backups will not work.
BACKUP DATABASE [YourDatabaseName]
TO DISK = 'C:\Backups\YourDatabaseName.bak'
WITH INIT, NAME = 'Full Backup - YourDatabaseName';
GO

-- STEP 3: Configure Transaction Log Backups
-- Regular log backups are mandatory in FULL recovery model.
-- They prevent uncontrolled transaction log (.ldf) growth and allow point-in-time restores.
-- Recommended frequency: every 5–15 minutes (depending on your RPO).
BACKUP LOG [YourDatabaseName]
TO DISK = 'C:\Backups\YourDatabaseName_Log.trn'
WITH INIT, NAME = 'Transaction Log Backup - YourDatabaseName';
GO

/********************************************************************************************
 NOTES:
 - Full Recovery Model requires BOTH full database backups and log backups.
 - To restore, you need: the last full backup + all subsequent log backups.
 - Store backups in a secure location (offsite/cloud if possible).
********************************************************************************************/