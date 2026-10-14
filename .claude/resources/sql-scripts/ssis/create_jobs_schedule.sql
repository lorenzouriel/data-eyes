/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Create and schedule a SQL Server Agent job named 'daily_jobs' that runs multiple 
--               SSIS packages for daily ETL processing.
-- Description:  This script:
--                 1. Creates the job.
--                 2. Adds multiple job steps for each SSIS package.
--                 3. Sets a schedule to run every minute.
--                 4. Attaches the job to the schedule.
--                 5. Associates the job with the server.
--                 6. Optionally starts the job.
************************************************************************************************/

-- ===============================================
-- Step 1: Create a new SQL Server Agent job
-- ===============================================
DECLARE @jobId UNIQUEIDENTIFIER

EXEC msdb.dbo.sp_add_job
    @job_name = 'daily_jobs',                        -- Name of the job
    @enabled = 1,                                    -- Job enabled by default
    @description = 'SSIS Job to process daily jobs', -- Job description
    @job_id = @jobId OUTPUT                           -- Output Job ID for later use

-- ===============================================
-- Step 2: Add job steps for each SSIS package
-- ===============================================
-- Note: /ISSERVER command specifies the SSIS package path and execution options

EXEC msdb.dbo.sp_add_jobstep
    @job_id = @jobId,
    @step_name = 'Daily Details',
    @subsystem = 'SSIS',
    @command = '/ISSERVER "\"\SSISDB\Database\ETL\.dtsx\"" /SERVER . /CHECKPOINTING OFF /REPORTING E',
    @on_success_action = 3 -- Go to next step

EXEC msdb.dbo.sp_add_jobstep
    @job_id = @jobId,
    @step_name = 'Daily Data',
    @subsystem = 'SSIS',
    @command = '/ISSERVER "\"\SSISDB\Database\ETL\.dtsx\"" /SERVER . /CHECKPOINTING OFF /REPORTING E',
    @on_success_action = 3

-- ===============================================
-- Step 3: Create a schedule for the job
-- ===============================================
DECLARE @scheduleId INT

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = 'MinutelySchedule',
    @enabled = 1,
    @freq_type = 4,             -- Daily schedule
    @freq_interval = 1,         -- Every day
    @freq_subday_type = 4,      -- Minutes
    @freq_subday_interval = 1,  -- Every 1 minute
    @active_start_time = 000000, -- Start at 00:00:00 AM
    @active_end_time = 235959,   -- End at 11:59:59 PM
    @schedule_id = @scheduleId OUTPUT

-- ===============================================
-- Step 4: Attach the job to the schedule
-- ===============================================
EXEC msdb.dbo.sp_attach_schedule
    @job_id = @jobId,
    @schedule_id = @scheduleId

-- ===============================================
-- Step 5: Associate the job with the server
-- ===============================================
EXEC msdb.dbo.sp_add_jobserver
    @job_name = 'daily_jobs',
    @server_name = @@SERVERNAME -- Uses current SQL Server instance

-- ===============================================
-- Step 6: Start the job (optional)
-- Uncomment if you want the job to start immediately
-- ===============================================
-- EXEC msdb.dbo.sp_start_job @job_id = @jobId