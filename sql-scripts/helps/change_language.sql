----------------------------------------------------------
-- 1. List All SQL Server Languages
----------------------------------------------------------
-- Returns all languages installed on the SQL Server instance
SELECT * 
FROM sys.syslanguages;
GO

----------------------------------------------------------
-- 2. Check Current Session Language
----------------------------------------------------------
-- Shows the language currently in use for this session
SELECT @@LANGUAGE AS CurrentLanguage;
GO

----------------------------------------------------------
-- 3. Check Default Language of SQL Server Logins
----------------------------------------------------------
-- Lists logins and their default language settings
SELECT 
    name, 
    default_language_name
FROM sys.server_principals
WHERE type IN ('S', 'U'); -- 'S' = SQL login, 'U' = Windows login
GO

----------------------------------------------------------
-- 4. Change Session Language
----------------------------------------------------------
-- Temporarily changes the language for the current session
SET LANGUAGE 'us_english';
GO

----------------------------------------------------------
-- 5. Change Default Language for a SQL Server Login
----------------------------------------------------------
-- Permanently changes the default language for the specified login
ALTER LOGIN [NT Service\MSSQLSERVER] 
WITH DEFAULT_LANGUAGE = us_english;
GO
----------------------------------------------------------