/*
List only currently running SQL Server Agent jobs
and show their active session (SPID) + SQL text
*/

SELECT 
    j.name                AS job_name,
    a.run_requested_date  AS start_time,
    a.job_id,
    r.session_id          AS spid,
    r.status,
    r.command,
    t.text                AS running_sql
FROM msdb.dbo.sysjobs j
JOIN msdb.dbo.sysjobactivity a 
    ON j.job_id = a.job_id
LEFT JOIN sys.dm_exec_requests r
    ON a.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE a.stop_execution_date IS NULL         -- job not marked as stopped
  AND a.start_execution_date IS NOT NULL    -- job has actually started
  AND r.session_id IS NOT NULL;             -- ensure there is an active SPID

-- Check Zombie Jobs
SELECT 
    j.name, 
    a.run_requested_date, 
    a.stop_execution_date, 
    a.job_id
FROM msdb.dbo.sysjobs j
JOIN msdb.dbo.sysjobactivity a 
    ON j.job_id = a.job_id
WHERE a.stop_execution_date IS NULL
  AND a.start_execution_date IS NOT NULL;


-- Stop Jobs
USE msdb;
GO
EXEC sp_stop_job @job_name = N'YourJobName';


EXEC msdb.dbo.sp_stop_job @job_id = '7B9753CF-A4FE-4CC8-AF5C-229AD137E0D1';