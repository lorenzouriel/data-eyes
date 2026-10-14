-- =============================================
-- Script: Failed Login Summary
-- Description: Reads SQL Server error logs to find failed login attempts,
--              counts occurrences and shows first/last times.
-- Author: Lorenzo Uriel
-- Date: 2025-08-20
-- =============================================

-- Temporary table to store error log info
DECLARE @LogFiles TABLE (
    LogNumber INT,
    StartDate DATETIME,
    SizeInBytes INT
);

-- Temporary table to store failed login entries
DECLARE @Data TABLE (
    [LogDate] DATETIME,
    [ProcessInfo] NVARCHAR(12),
    [Text] NVARCHAR(3999)
);

-- Populate log files table (use 1 for SQL Server error logs)
INSERT INTO @LogFiles
EXEC sys.xp_enumerrorlogs 1;

-- Variables for looping through logs
DECLARE 
    @Counter INT = 0,
    @Total INT = (SELECT COUNT(*) FROM @LogFiles);

-- Loop through all error logs to get 'login failed' entries
WHILE (@Counter < @Total)
BEGIN
    INSERT INTO @Data
    EXEC sys.sp_readerrorlog @Counter, 1, 'login failed';
    
    SET @Counter += 1;
END;

-- Summarize failed login attempts
SELECT
    MIN(LogDate) AS FirstOccurrence,
    MAX(LogDate) AS LastOccurrence,
    -- Extract the message text before any '[' character (usually username info)
    SUBSTRING([Text], 1, IIF(CHARINDEX('[', [Text]) = 0, LEN([Text]), CHARINDEX('[', [Text]) - 1)) AS MessageText,
    COUNT(DISTINCT [Text]) AS Occurrences
FROM
    @Data
GROUP BY
    SUBSTRING([Text], 1, IIF(CHARINDEX('[', [Text]) = 0, LEN([Text]), CHARINDEX('[', [Text]) - 1))
ORDER BY
    Occurrences DESC;