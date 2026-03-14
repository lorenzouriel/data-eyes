### Job Execution Count (Last 7 Days)
```sql
SELECT 
	job.name AS JobName,
	COUNT(run.run_date) AS ExecutionCount
FROM msdb.dbo.sysjobs AS job
INNER JOIN msdb.dbo.sysjobhistory AS run
ON job.job_id = run.job_id
WHERE run.run_date >= CONVERT(VARCHAR, GETDATE() - 7, 112)  -- Last 7 days
GROUP BY job.name
ORDER BY ExecutionCount DESC;
```
* **Purpose:** To count how many times each SQL Server Agent job executed in the last 7 days.
* **Metric:** Number of job executions per job.
* **Use case:** Monitoring job activity frequency and detecting anomalies in job execution patterns.
* **Reference:** `msdb.dbo.sysjobs`, `msdb.dbo.sysjobhistory`.

### Currently Running Jobs
```sql
SELECT DISTINCT 
       job.name AS JobName,
       activity.run_requested_date AS StartTime,
       DATEDIFF(SECOND, activity.run_requested_date, GETDATE()) AS RunDurationSeconds
FROM msdb.dbo.sysjobs AS job
INNER JOIN msdb.dbo.sysjobactivity AS activity
    ON job.job_id = activity.job_id
WHERE activity.run_requested_date IS NOT NULL
  AND activity.stop_execution_date IS NULL
ORDER BY activity.run_requested_date DESC;
```
* **Purpose:** To identify jobs that are currently running.
* **Metric:** Start time and duration of running jobs in seconds.
* **Use case:** Tracking live job execution for monitoring or troubleshooting long-running processes.
* **Reference:** `msdb.dbo.sysjobs`, `msdb.dbo.sysjobactivity`.

### Scheduled and Running Jobs Overview
```sql
SELECT
       job.name AS JobName,
       CASE
           WHEN activity.run_requested_date IS NULL THEN 'Scheduled'
           ELSE 'Running'
       END AS JobStatus,
       schedule.next_run_date AS NextRunDate,
       schedule.next_run_time AS NextRunTime
FROM msdb.dbo.sysjobs AS job
LEFT JOIN msdb.dbo.sysjobactivity AS activity ON job.job_id = activity.job_id
LEFT JOIN msdb.dbo.sysjobschedules AS schedule ON job.job_id = schedule.job_id
WHERE  schedule.next_run_date IS NOT NULL       -- Scheduled jobs
ORDER BY schedule.next_run_date, schedule.next_run_time
```
* **Purpose:** To provide a snapshot of both running and scheduled jobs.
* **Metric:** Job status (Running or Scheduled) and next scheduled run.
* **Use case:** Monitoring upcoming and in-progress jobs to manage workloads efficiently.
* **Reference:** `msdb.dbo.sysjobs`, `msdb.dbo.sysjobactivity`, `msdb.dbo.sysjobschedules`.

### Job Run History
```sql
SELECT 
	job.name AS JobName,
	run.run_date AS RunDate,
	run.run_duration AS RunDuration
FROM msdb.dbo.sysjobs AS job
INNER JOIN msdb.dbo.sysjobhistory AS run
ON job.job_id = run.job_id
WHERE run.step_id = 0  -- 0 indicates job level information
ORDER BY run.run_date DESC;
```
* **Purpose:** To view the historical execution of jobs.
* **Metric:** Job run date and duration.
* **Use case:** Reviewing past job executions for auditing, performance tracking, or debugging.
* **Reference:** `msdb.dbo.sysjobs`, `msdb.dbo.sysjobhistory`.

### Failed Job Runs
```sql
SELECT 
    job.name AS JobName,
    run.run_date AS RunDate,
    run.run_time AS RunTime,
    run.run_duration AS RunDuration,
    run.message AS ErrorMessage
FROM msdb.dbo.sysjobs AS job
INNER JOIN msdb.dbo.sysjobhistory AS run
ON job.job_id = run.job_id
WHERE run.run_status = 0  -- 0 indicates failure
ORDER BY run.run_date DESC;
```
* **Purpose:** To identify jobs that failed during execution.
* **Metric:** Run date, time, duration, and error message for failed jobs.
* **Use case:** Detecting and troubleshooting job failures quickly.
* **Reference:** `msdb.dbo.sysjobs`, `msdb.dbo.sysjobhistory`.