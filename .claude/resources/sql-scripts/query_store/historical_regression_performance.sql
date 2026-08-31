-- Queries with historical regression in performance
-- When you want to compare recent execution to historical execution, the following query compares query execution based on period of execution. 
-- In this particular example, the query compares execution in recent period (1 hour) vs. history period (last day) and identifies those that introduced additional_duration_workload. 
-- This metric is calculated as a difference between recent average execution and history average execution multiplied by the number of recent executions. 
-- It represents how much extra duration these recent executions introduced, compared to the history:
--- "Recent" workload - last 1 hour
DECLARE @recent_start_time DATETIMEOFFSET;
DECLARE @recent_end_time DATETIMEOFFSET;

SET @recent_start_time = DATEADD(hour, - 1, SYSUTCDATETIME());
SET @recent_end_time = SYSUTCDATETIME();

--- "History" workload
DECLARE @history_start_time DATETIMEOFFSET;
DECLARE @history_end_time DATETIMEOFFSET;

SET @history_start_time = DATEADD(hour, - 24, SYSUTCDATETIME());
SET @history_end_time = SYSUTCDATETIME();

WITH hist AS (
    SELECT p.query_id query_id,
        ROUND(ROUND(CONVERT(FLOAT, SUM(rs.avg_duration * rs.count_executions)) * 0.001, 2), 2) AS total_duration,
        SUM(rs.count_executions) AS count_executions,
        COUNT(DISTINCT p.plan_id) AS num_plans
    FROM sys.query_store_runtime_stats AS rs
    INNER JOIN sys.query_store_plan AS p
        ON p.plan_id = rs.plan_id
    WHERE (
        rs.first_execution_time >= @history_start_time
        AND rs.last_execution_time < @history_end_time
    )
    OR (
        rs.first_execution_time <= @history_start_time
        AND rs.last_execution_time > @history_start_time
    )
    OR (
        rs.first_execution_time <= @history_end_time
        AND rs.last_execution_time > @history_end_time
    )
    GROUP BY p.query_id
),
recent AS (
    SELECT p.query_id query_id,
        ROUND(ROUND(CONVERT(FLOAT, SUM(rs.avg_duration * rs.count_executions)) * 0.001, 2), 2) AS total_duration,
        SUM(rs.count_executions) AS count_executions,
        COUNT(DISTINCT p.plan_id) AS num_plans
    FROM sys.query_store_runtime_stats AS rs
    INNER JOIN sys.query_store_plan AS p
        ON p.plan_id = rs.plan_id
    WHERE (
        rs.first_execution_time >= @recent_start_time
        AND rs.last_execution_time < @recent_end_time
    )
    OR (
        rs.first_execution_time <= @recent_start_time
        AND rs.last_execution_time > @recent_start_time
    )
    OR (
        rs.first_execution_time <= @recent_end_time
        AND rs.last_execution_time > @recent_end_time
    )
    GROUP BY p.query_id
    )
SELECT results.query_id AS query_id,
    results.query_text AS query_text,
    results.additional_duration_workload AS additional_duration_workload,
    results.total_duration_recent AS total_duration_recent,
    results.total_duration_hist AS total_duration_hist,
    ISNULL(results.count_executions_recent, 0) AS count_executions_recent,
    ISNULL(results.count_executions_hist, 0) AS count_executions_hist
FROM (
    SELECT hist.query_id AS query_id,
        qt.query_sql_text AS query_text,
        ROUND(CONVERT(FLOAT, recent.total_duration / recent.count_executions - hist.total_duration / hist.count_executions) * (recent.count_executions), 2) AS additional_duration_workload,
        ROUND(recent.total_duration, 2) AS total_duration_recent,
        ROUND(hist.total_duration, 2) AS total_duration_hist,
        recent.count_executions AS count_executions_recent,
        hist.count_executions AS count_executions_hist
    FROM hist
    INNER JOIN recent
        ON hist.query_id = recent.query_id
    INNER JOIN sys.query_store_query AS q
        ON q.query_id = hist.query_id
    INNER JOIN sys.query_store_query_text AS qt
        ON q.query_text_id = qt.query_text_id
) AS results
WHERE additional_duration_workload > 0
ORDER BY additional_duration_workload DESC
OPTION (MERGE JOIN);