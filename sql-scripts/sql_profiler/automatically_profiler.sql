/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Automate SQL Profiler tracing, monitor long-running queries, and optionally
--               delete the trace file. Integrated with SQL Server Agent for alerting.
-- Description:  This script contains:
--               1. Procedure creation: AutomaticallyProfiler
--               2. Execution of the procedure
--               3. Checking the trace file for queries longer than 30 seconds
--               4. Deleting the profiler trace file
************************************************************************************************/

-- ========================================================
-- 1. Create Procedure: AutomaticallyProfiler
-- ========================================================
USE [your_database];  -- Replace with your target database
GO

CREATE PROCEDURE [dbo].[AutomaticallyProfiler]  
    @RunTime INT = 120  -- Duration of the trace in minutes
AS
BEGIN
    -- ================================================
    -- Variables for trace creation and control
    -- ================================================
    DECLARE @rc INT;              -- Return code from trace procedures
    DECLARE @TraceID INT;         -- Trace ID for the created trace
    DECLARE @maxfilesize BIGINT;  -- Maximum size of the trace file
    DECLARE @Now DATETIME;        -- Current datetime
    DECLARE @StopTime DATETIME;   -- Stop datetime for the trace
    DECLARE @FQFileName NVARCHAR(100); -- Full trace file path
    DECLARE @FileStamp NVARCHAR(25);   -- Timestamp for filename

    -- Set time and file name
    SET @Now = GETDATE();
    SET @StopTime = DATEADD(MI, @RunTime, @Now);
    SET @FQFileName = 'C:\Profiler\TraceProfiler_';  -- Ensure folder exists
    SET @FileStamp =
        CAST(DATEPART(YEAR, GETDATE()) AS NVARCHAR) +
        RIGHT('0' + CAST(DATEPART(MONTH, GETDATE()) AS NVARCHAR), 2) +
        RIGHT('0' + CAST(DATEPART(DAY, GETDATE()) AS NVARCHAR), 2);
    SET @FQFileName = @FQFileName + @FileStamp;
    SET @maxfilesize = 500;  -- Max file size in MB

    -- ================================================
    -- Create the trace
    -- ================================================
    EXEC @rc = sp_trace_create @TraceID OUTPUT, 0, @FQFileName, @maxfilesize, @StopTime;
    IF (@rc != 0) GOTO error;

    -- ================================================
    -- Configure trace events
    -- ================================================
    DECLARE @on BIT = 1;

    -- RPC:Completed (EventClass 10)
    EXEC sp_trace_setevent @TraceID, 10, 1, @on;   -- TextData
    EXEC sp_trace_setevent @TraceID, 10, 12, @on;  -- SPID
    EXEC sp_trace_setevent @TraceID, 10, 13, @on;  -- Duration

    -- SQL:BatchCompleted (EventClass 12)
    EXEC sp_trace_setevent @TraceID, 12, 1, @on;   -- TextData
    EXEC sp_trace_setevent @TraceID, 12, 12, @on;  -- SPID
    EXEC sp_trace_setevent @TraceID, 12, 13, @on;  -- Duration

    -- ================================================
    -- Optional filters
    -- ================================================
    DECLARE @intfilter INT = 50;  -- Duration threshold
    EXEC sp_trace_setfilter @TraceID, 12, 0, 4, @intfilter; -- Filter: Duration > 50
    EXEC sp_trace_setfilter @TraceID, 35, 0, 7, N'Master';  -- Filter: Database = Master

    -- ================================================
    -- Start the trace
    -- ================================================
    EXEC sp_trace_setstatus @TraceID, 1;
    SELECT TraceID = @TraceID;  -- Return Trace ID
    GOTO finish;

error:
    SELECT ErrorCode = @rc;  -- Return error code if creation fails

finish:
END;
GO

-- ========================================================
-- 2. Execute Procedure
-- ========================================================
USE [your_database];
GO

DECLARE @return_value INT;

EXEC @return_value = [dbo].[AutomaticallyProfiler];

SELECT 'Return Value' = @return_value;
GO

-- ========================================================
-- 3. Check Profiler Trace File for Long Queries (>30s)
-- ========================================================
DECLARE @FQFileName NVARCHAR(100);
DECLARE @FileStamp NVARCHAR(25);

SET @FQFileName = 'C:\Profiler\TraceProfiler_';
SET @FileStamp =
    CAST(DATEPART(YEAR, GETDATE()) AS NVARCHAR) +
    RIGHT('0' + CAST(DATEPART(MONTH, GETDATE()) AS NVARCHAR), 2) +
    RIGHT('0' + CAST(DATEPART(DAY, GETDATE()) AS NVARCHAR), 2);
SET @FQFileName = @FQFileName + @FileStamp + '.trc';

DECLARE @DurationCount INT;

-- Count queries taking longer than 30 seconds (30,000,000 microseconds)
SELECT @DurationCount = ISNULL(COUNT(Duration), 0)
FROM fn_trace_gettable(@FQFileName, 1)
WHERE [Duration] > 30000000;

-- Raise an error if long queries exist
IF @DurationCount > 0
BEGIN
    RAISERROR('Some queries took more than 30 seconds', 16, 1);
END;

-- ========================================================
-- 4. Delete Profiler Trace File
-- ========================================================
DECLARE @FilePath NVARCHAR(100) = 'C:\Profiler\';
DECLARE @FileName NVARCHAR(100) = 'TraceProfiler_';

SET @FileName =
    @FileName +
    CAST(DATEPART(YEAR, GETDATE()) AS NVARCHAR) +
    RIGHT('0' + CAST(DATEPART(MONTH, GETDATE()) AS NVARCHAR), 2) +
    RIGHT('0' + CAST(DATEPART(DAY, GETDATE()) AS NVARCHAR), 2) +
    '.trc';

DECLARE @Cmd NVARCHAR(200);
SET @Cmd = 'DEL "' + @FilePath + @FileName + '"';

EXEC xp_cmdshell @Cmd;