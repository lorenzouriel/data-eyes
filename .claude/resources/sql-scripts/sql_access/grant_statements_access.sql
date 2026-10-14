/********************************************************************************************
 Script: Create Database User and Grant Schema Permissions
 Description: Creates a database user if it does not exist and grants standard DML
              permissions (SELECT, INSERT, UPDATE, DELETE) on the dbo schema.
********************************************************************************************/

-- Switch to the target database
USE [dev_os];
GO

-- Create the database user if it does not exist
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = 'dev')
BEGIN
    CREATE USER [dev] FOR LOGIN [dev];
    -- Explanation: Creates a database-level user 'dev' linked to the server login 'dev'.
END
GO

-- Grant standard DML permissions on the dbo schema
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [dev];
-- Explanation: Allows the user 'dev' to read and modify all objects in the dbo schema.
GO
