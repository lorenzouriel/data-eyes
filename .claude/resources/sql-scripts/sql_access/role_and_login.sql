/********************************************************************************************
 Script: Create Login, User, Role, and Assign Permissions
 Description: Creates a SQL Server login, a database user, a role, grants schema-level
              permissions, and assigns the user to the role.
********************************************************************************************/

-- Create a SQL Server login
USE master;
GO
CREATE LOGIN Test123 WITH PASSWORD = 'Test';  
-- Explanation: Creates a server-level login named 'Test123' with the specified password.
GO

-- Create a database user for the login
USE AdventureWorks2019;
GO
CREATE USER Test123 FOR LOGIN Test123;  
-- Explanation: Creates a database-level user linked to the server login.
GO

-- Create a database role
CREATE ROLE RoleTest;  
-- Explanation: Creates a new database role called 'RoleTest' to manage permissions.
GO

-- Grant SELECT permission on a specific schema to the role
GRANT SELECT ON SCHEMA::HumanResources TO RoleTest;  
-- Explanation: Allows any member of 'RoleTest' to select data from all objects in the HumanResources schema.
GO

-- Add the user to the role
ALTER ROLE RoleTest ADD MEMBER Test123;  
-- Explanation: Assigns the user 'Test123' to the role 'RoleTest', giving them the granted permissions.
GO