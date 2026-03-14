/********************************************************************************************
 Script: Grant Database Access and Change Ownership
 Description: Grants a user access to a database and changes the database owner.
********************************************************************************************/

-- =Grant the user permission to view the database
USE [master];
GO
GRANT VIEW [dev_os] DATABASE TO [dev];  
-- Explanation: Gives the user 'dev' permission to view metadata of the database 'dev_os'.
GO

-- Change the database owner
USE [master];
GO
ALTER AUTHORIZATION ON DATABASE::[dev_os] TO [dev];  
-- Explanation: Sets 'dev' as the owner of the database 'dev_os'.
GO
