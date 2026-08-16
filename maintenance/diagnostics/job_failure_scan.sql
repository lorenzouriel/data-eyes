-- #######################
-- SQL AGENT JOB HEALTH — live observation, read-only, instance-wide
-- Purpose: Most recent run outcome + failure count per enabled job — ports
--          monitor/docs/jobs_monitoring.md's "Failed Job Runs"/"Job Run History"
--          queries into a single severity-classified, MCP-tool-consumable form.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> maintenance.jobs
-- Note: jobs are instance-level, not per-database, so there is no
--       @DatabaseName parameter here (unlike the other diagnostics/ scripts).
-- #######################

;WITH RecentRuns AS (
    SELECT
        j.job_id,
        j.name AS JobName,
        h.run_status,
        msdb.dbo.agent_datetime(h.run_date, h.run_time) AS RunDateTime,
        h.run_duration AS RunDuration,
        h.message AS RunMessage,
        ROW_NUMBER() OVER (PARTITION BY j.job_id ORDER BY msdb.dbo.agent_datetime(h.run_date, h.run_time) DESC) AS rn
    FROM msdb.dbo.sysjobs j
    INNER JOIN msdb.dbo.sysjobhistory h ON h.job_id = j.job_id AND h.step_id = 0
    WHERE j.enabled = 1
),
LastRun AS (
    SELECT * FROM RecentRuns WHERE rn = 1
),
FailureCounts AS (
    SELECT
        job_id,
        COUNT(*) AS FailuresLast7Days
    FROM RecentRuns
    WHERE run_status = 0
        AND RunDateTime >= DATEADD(DAY, -7, GETDATE())
    GROUP BY job_id
),
Base AS (
    SELECT
        lr.JobName,
        lr.RunDateTime AS LastRunDateTime,
        CASE lr.run_status
            WHEN 0 THEN 'Failed'
            WHEN 1 THEN 'Succeeded'
            WHEN 2 THEN 'Retry'
            WHEN 3 THEN 'Canceled'
            ELSE 'Unknown'
        END AS LastRunStatus,
        lr.RunMessage AS LastRunMessage,
        ISNULL(fc.FailuresLast7Days, 0) AS FailuresLast7Days,
        CASE
            WHEN lr.run_status = 0 THEN 'CRITICAL'
            WHEN ISNULL(fc.FailuresLast7Days, 0) > 0 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM LastRun lr
    LEFT JOIN FailureCounts fc ON fc.job_id = lr.job_id
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, LastRunDateTime DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
