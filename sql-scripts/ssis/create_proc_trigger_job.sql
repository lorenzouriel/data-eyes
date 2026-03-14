/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-07-10
-- Purpose:      Trigger the SQL Server Agent job named 'job_name'.
-- Description:  This procedure checks if the specified job exists and is enabled,
--               stops it if already running (errors ignored), and then starts the job.
--               All errors during stop/start are safely suppressed.
************************************************************************************************/

CREATE PROCEDURE [dbo].[job_name]  
AS  
BEGIN  
    -- ===============================================
    -- Step 1: Check if the job exists and is enabled
    -- ===============================================
    IF EXISTS (  
        SELECT 1  
        FROM msdb.dbo.sysjobs sj  
        JOIN msdb.dbo.sysjobschedules sjs ON sj.job_id = sjs.job_id  
        JOIN msdb.dbo.sysjobs_view sjv ON sj.job_id = sjv.job_id  
        WHERE sj.name = 'job_name'  
          AND sjv.enabled = 1  -- Only consider enabled jobs
    )  
    BEGIN  
        -- ===============================================
        -- Step 2: Stop the job if currently running
        -- Errors are suppressed to avoid interruption
        -- ===============================================
        BEGIN TRY  
            EXEC msdb.dbo.sp_stop_job @job_name = 'job_name';  
        END TRY  
        BEGIN CATCH  
            -- Ignore any errors during stop attempt
        END CATCH  
    END  
  
    -- ===============================================
    -- Step 3: Start the job
    -- Errors are suppressed to avoid interruption
    -- ===============================================
    BEGIN TRY  
        EXEC msdb.dbo.sp_start_job @job_name = 'job_name';  
    END TRY  
    BEGIN CATCH  
        -- Ignore any errors during start attempt
    END CATCH  
END
