-- Revoke ability to connect to the database
REVOKE CONNECT TO [user.name];

-- Drop the user from the database
DROP USER [user.name];

-- Then drop the login at the server level
DROP LOGIN [user.name];

-- If you just want to disable the login (instead of deleting it):
ALTER LOGIN [user.name] DISABLE;

-- ##############
-- ERROR
-- Msg 15138, Level 16, State 1, Line 5 
-- The database principal owns a schema in the database, and cannot be dropped. 
-- ##############
-- Check which schema(s) the user owns
SELECT 
	s.name AS SchemaName, 
	u.name AS OwnerName
FROM sys.schemas s
JOIN sys.database_principals u ON s.principal_id = u.principal_id
WHERE u.name = 'user.name';

-- Change schema ownership to another user (commonly dbo)
ALTER AUTHORIZATION ON SCHEMA::[db_datareader] TO dbo;

-- Drop the user from the database
DROP USER [user.name];