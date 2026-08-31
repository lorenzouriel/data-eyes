/********************************************************************************************
 Script: Database Access Control and Ownership Change
 Description: Denies the ability to view all databases and changes the database owner.
********************************************************************************************/

-- Deny permission to view all databases
USE [master];
GO
DENY VIEW ANY DATABASE TO [lorenzo.dev];  
-- Explanation: Prevents the user 'lorenzo.dev' from seeing databases they do not own.
GO

-- Change the owner of a specific database
USE [master];
GO
ALTER AUTHORIZATION ON DATABASE::[database] TO [lorenzo.dev];  
-- Explanation: Sets 'lorenzo.dev' as the owner of the specified database.
-- Replace [database] with the actual database name.
GO