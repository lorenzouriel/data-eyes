/********************************************************************************************
 Script: Check SQL Server Database Recovery Model
 Purpose: Verify the recovery model of one or all databases.
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-- Check the recovery model of a specific database
SELECT 
    name AS DatabaseName,                 -- Database name
    recovery_model_desc AS RecoveryModel  -- Recovery model (FULL, SIMPLE, BULK_LOGGED)
FROM sys.databases
WHERE name = 'YourDatabaseName';
GO

-- Check the recovery model of all databases on the server
SELECT 
    name AS DatabaseName,                -- Database name
    recovery_model_desc AS RecoveryModel  -- Recovery model (FULL, SIMPLE, BULK_LOGGED)
FROM sys.databases;
GO

/********************************************************************************************
 NOTES:
 - RecoveryModel can be: FULL, SIMPLE or BULK_LOGGED.
 - Use this query after changing a database to FULL to confirm the change.
 - Always verify before setting up transaction log backups.
********************************************************************************************/