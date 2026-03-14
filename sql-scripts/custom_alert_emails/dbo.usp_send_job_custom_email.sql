-- =============================================
-- PROCEDURE: dbo.usp_send_job_custom_email
-- PURPOSE: Sends a fully formatted HTML email with the latest
--          SQL Server Agent job execution details.
-- PARAMETERS:
--   @job_name SYSNAME - Name of the SQL Agent Job
-- NOTES:
-- - Uses sysjobs, sysjobhistory, sysjobsteps in msdb
-- - Sends HTML email via Database Mail profile
-- Author: Lorenzo Uriel
-- Date: 2025-08-19
-- =============================================
CREATE PROCEDURE dbo.usp_send_job_custom_email  
    @job_name SYSNAME  -- Input: Name of the job to report
AS  
BEGIN  
    SET NOCOUNT ON;  -- Avoid extra result sets

    -- ========================
    -- DECLARE VARIABLES
    -- ========================
    DECLARE  
        @job_id UNIQUEIDENTIFIER,            -- Job identifier
        @run_datetime DATETIME,              -- Job start datetime
        @duration VARCHAR(20),               -- Job duration as formatted string
        @start_time TIME,                    -- Job start time
        @status VARCHAR(100),                -- Job status (Succeeded/Failed/Unknown)
        @executed_by SYSNAME,                -- SQL Server login executing the job
        @server_name SYSNAME = CONVERT(SYSNAME, SERVERPROPERTY('MachineName')), -- Server name
        @last_step NVARCHAR(128),            -- Last step name
        @first_step NVARCHAR(128),           -- First step name
        @html_body NVARCHAR(MAX);            -- HTML email content

    -- ========================
    -- GET JOB ID
    -- ========================
    SELECT @job_id = job_id
    FROM msdb.dbo.sysjobs
    WHERE name = @job_name;

    IF @job_id IS NULL
    BEGIN
        RAISERROR('Job not found.', 16, 1);  -- Raise error if job does not exist
        RETURN;
    END

    -- ========================
    -- GET LATEST JOB RUN INFORMATION
    -- ========================
    DECLARE @run_date INT, @run_time INT, @run_duration INT, @message NVARCHAR(MAX);

    SELECT TOP 1  
        @run_date = run_date,  
        @run_time = run_time,  
        @run_duration = run_duration,  
        @message = message  
    FROM msdb.dbo.sysjobhistory  
    WHERE job_id = @job_id AND step_id = 0  -- Step_id = 0 indicates job outcome
    ORDER BY instance_id DESC;

    -- ========================
    -- FORMAT DATE, TIME AND DURATION
    -- ========================
    SELECT @run_datetime = CONVERT(DATETIME,
        STUFF(STUFF(CONVERT(CHAR(8), @run_date), 5, 0, '-'), 8, 0, '-') + ' ' +
        STUFF(STUFF(RIGHT('000000' + CAST(@run_time AS VARCHAR(6)), 6), 3, 0, ':'), 6, 0, ':')
    );

    SELECT @duration =
        CAST(@run_duration / 10000 AS VARCHAR) + 'h ' +
        CAST((@run_duration % 10000) / 100 AS VARCHAR) + 'm ' +
        CAST(@run_duration % 100 AS VARCHAR) + 's';

    -- ========================
    -- GET FIRST AND LAST STEP NAMES AND EXECUTOR
    -- ========================
    SELECT TOP 1  
        @executed_by = suser_sname(),  
        @first_step = (SELECT TOP 1 step_name FROM msdb.dbo.sysjobsteps WHERE job_id = @job_id ORDER BY step_id),  
        @last_step = (SELECT TOP 1 step_name FROM msdb.dbo.sysjobsteps WHERE job_id = @job_id ORDER BY step_id DESC);

    -- ========================
    -- DETERMINE JOB STATUS AND STYLIZE
    -- ========================
    IF @message LIKE '%succeeded%'  
        SET @status = '<span style="color:green;font-weight:bold">Succeeded</span>';  
    ELSE IF @message LIKE '%failed%'  
        SET @status = '<span style="color:red;font-weight:bold">Failed</span>';  
    ELSE  
        SET @status = '<span style="color:orange;font-weight:bold">Unknown</span>';

    -- ========================
    -- BUILD HTML EMAIL BODY
    -- ========================
    SET @html_body =
    N'<html>
    <head>
    <style>
    body { font-family: Segoe UI, sans-serif; color: #333; }
    h2 { color: #2e6c80; }
    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
    </style>
    </head>
    <body>
    <h2>SQL Server Job Notification</h2>
    <table>
    <tr><th>Job Name</th><td>' + @job_name + '</td></tr>
    <tr><th>Status</th><td>' + @status + '</td></tr>
    <tr><th>Run Date</th><td>' + CONVERT(VARCHAR, @run_datetime, 107) + '</td></tr>
    <tr><th>Start Time</th><td>' + CONVERT(VARCHAR, @run_datetime, 114) + '</td></tr>
    <tr><th>Duration</th><td>' + @duration + '</td></tr>
    <tr><th>Executed By</th><td>' + @executed_by + '</td></tr>
    <tr><th>Last Step</th><td>' + ISNULL(@last_step, '-') + '</td></tr>
    <tr><th>Initial Step</th><td>' + ISNULL(@first_step, '-') + '</td></tr>
    <tr><th>Server</th><td>' + @server_name + '</td></tr>
    </table>
    <p style="margin-top: 20px;">Message: ' + @message + '</p>
    </body>
    </html>';

    DECLARE @subject NVARCHAR(255) = '[SQL Job Completed] ' + @job_name;

    -- ========================
    -- SEND THE EMAIL
    -- ========================
    EXEC msdb.dbo.sp_send_dbmail
        @profile_name = 'SQL Alerts',        -- Database Mail profile
        @recipients = 'lorenzouriel@sqlserver.com', -- Recipient(s)
        @subject = @subject,
        @body_format = 'HTML',
        @body = @html_body;
END

-- Execute the procedure for a specific SQL Agent Job
-- EXEC dbo.usp_send_job_custom_email @job_name = 'job_name';