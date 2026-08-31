/********************************************************************************************
 Script: SQL Server Login Information and Last Login Tracking
 Description: 
   - Retrieves server login information
   - Tracks granted permissions
   - Builds a historical table of last login times for users
 Author: Lorenzo Uriel
 Date: 2025-08-20
********************************************************************************************/

-------------------------
-- STEP 1: Basic information about users/logins
-------------------------
-- List all logins with basic info
EXEC sp_helplogins;

-- List SQL logins and creation dates
SELECT name, accdate 
FROM sys.syslogins;

-- SQL logins from sys.sql_logins view
SELECT * 
FROM sys.sql_logins;

-------------------------
-- STEP 2: Check granted permissions for users
-------------------------
SELECT
   S.name,
   S.loginname,
   S.password,
   L.sid,
   L.is_disabled,
   S.createdate,
   S.denylogin,
   S.hasaccess,
   S.isntname,
   S.isntgroup,
   S.isntuser,
   S.sysadmin,
   S.securityadmin,
   S.serveradmin,
   S.processadmin,
   S.diskadmin,
   S.dbcreator,
   S.bulkadmin
FROM sys.syslogins S
LEFT JOIN sys.sql_logins L ON S.sid = L.sid;

-------------------------
-- STEP 3: Last login for each user
-------------------------
SELECT 
    login_name AS [Login], 
    MAX(login_time) AS [Last Login Time] 
FROM sys.dm_exec_sessions 
GROUP BY login_name;

-------------------------
-- STEP 4: Extract logins from SQL Server error logs
-------------------------
-- Temporary tables to store log file info and parsed login entries
IF OBJECT_ID('tempdb..#Arquivos_Log') IS NOT NULL DROP TABLE #Arquivos_Log;
CREATE TABLE #Arquivos_Log ( 
    [idLog] INT, 
    [dtLog] NVARCHAR(30) COLLATE SQL_Latin1_General_CP1_CI_AI, 
    [tamanhoLog] INT 
);

IF OBJECT_ID('tempdb..#Dados') IS NOT NULL DROP TABLE #Dados;
CREATE TABLE #Dados (
    [LogDate] DATETIME, 
    [ProcessInfo] NVARCHAR(50) COLLATE SQL_Latin1_General_CP1_CI_AI, 
    [Text] NVARCHAR(MAX) COLLATE SQL_Latin1_General_CP1_CI_AI,
    [User] AS (SUBSTRING(REPLACE([Text], 'Login succeeded for user ''', ''), 1, CHARINDEX('''', REPLACE([Text], 'Login succeeded for user ''', '')) - 1))
);

-- Populate log files
INSERT INTO #Arquivos_Log
EXEC sys.sp_enumerrorlogs;

-- Loop through all error logs and extract successful login entries
DECLARE @Contador INT = 0,
        @Total INT = (SELECT COUNT(*) FROM #Arquivos_Log);

WHILE (@Contador < @Total)
BEGIN
    INSERT INTO #Dados (LogDate, ProcessInfo, [Text])
    EXEC master.dbo.xp_readerrorlog @Contador, 1, N'Login succeeded for user', NULL, NULL, NULL;

    SET @Contador += 1;
END;

-- Store the last login date per user
IF OBJECT_ID('tempdb..#UltimoLogin') IS NOT NULL DROP TABLE #UltimoLogin;
CREATE TABLE #UltimoLogin (
    [User] VARCHAR(128) COLLATE SQL_Latin1_General_CP1_CI_AI NOT NULL,
    LogDate DATETIME NOT NULL
);

INSERT INTO #UltimoLogin
SELECT 
    [User], 
    MAX(LogDate) AS LogDate
FROM #Dados
GROUP BY [User];

-------------------------
-- STEP 5: Maintain historical LastLogin table
-------------------------
-- Create table if it doesn't exist
IF OBJECT_ID('dbo.LastLogin') IS NULL
BEGIN
    CREATE TABLE dbo.LastLogin (
        Username VARCHAR(128) COLLATE SQL_Latin1_General_CP1_CI_AI NOT NULL,
        CreateDate DATETIME,
        LastLogin DATETIME NULL,
        DaysSinceLastLogin AS (DATEDIFF(DAY, ISNULL(LastLogin, CreateDate), CONVERT(DATE, GETDATE())))
    );
END;

-- Insert new logins into historical table
INSERT INTO dbo.LastLogin (Username, CreateDate)
SELECT
    [name],
    create_date
FROM sys.server_principals A
LEFT JOIN dbo.LastLogin B ON A.[name] COLLATE SQL_Latin1_General_CP1_CI_AI = B.Username
WHERE
    is_fixed_role = 0
    AND [name] NOT LIKE 'NT %'
    AND [name] NOT LIKE '##%'
    AND B.Username IS NULL
    AND A.[type] IN ('S', 'U');

-- Update last login times in historical table
UPDATE A
SET A.LastLogin = B.LogDate
FROM dbo.LastLogin A
JOIN #UltimoLogin B ON A.Username = B.[User]
WHERE I