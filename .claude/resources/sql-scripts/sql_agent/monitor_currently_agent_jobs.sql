/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Monitor currently running SQL Server Agent jobs.
-- Description:  These queries help identify jobs that are executing, their start times, 
--               and current execution status.
************************************************************************************************/

-- ============================================================
-- Step 1: List all jobs that are currently running (no stop time)
-- ============================================================
SELECT 
    j.name AS job_name,              -- Name of the SQL Server Agent job
    ja.start_execution_date          -- When the job started execution
FROM msdb.dbo.sysjobactivity ja
JOIN msdb.dbo.sysjobs j 
    ON ja.job_id = j.job_id
WHERE ja.stop_execution_date IS NULL     -- Job has not yet stopped
  AND ja.start_execution_date IS NOT NULL; -- Job has started

-- ============================================================
-- Step 2: Use built-in stored procedure to get executing jobs
-- ============================================================
-- Execution status: 1 = Executing
EXEC msdb.dbo.sp_help_job 
    @execution_status = 1;

-- ============================================================
-- Step 3: Detailed check for a specific job by Job ID
-- ============================================================
USE msdb;
GO

SELECT 
    j.job_id,                        -- Job identifier
    j.name AS job_name,               -- Name of the job
    ja.start_execution_date,          -- Start date/time
    ja.stop_execution_date,           -- Stop date/time
    CASE 
        WHEN ja.start_execution_date IS NOT NULL AND ja.stop_execution_date IS NULL THEN 'Running'
        ELSE 'Not Running'
    END AS job_status                 -- Current status derived from start/stop dates
FROM msdb.dbo.sysjobactivity ja
INNER JOIN msdb.dbo.sysjobs j 
    ON ja.job_id = j.job_id
WHERE j.job_id = '6B56A2A5-295C-4D63-A3CE-47DA802560BE'; -- Replace with desired Job ID
-- ============================================================