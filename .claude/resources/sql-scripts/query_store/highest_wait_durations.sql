-- Highest wait durations
-- This query returns the top 10 queries with the highest wait durations for the last hour:
SELECT TOP 10 qt.query_text_id,
    q.query_id,
    p.plan_id,
    sum(total_query_wait_time_ms) AS sum_total_wait_ms
FROM sys.query_store_wait_stats ws
INNER JOIN sys.query_store_plan p
    ON ws.plan_id = p.plan_id
INNER JOIN sys.query_store_query q
    ON p.query_id = q.query_id
INNER JOIN sys.query_store_query_text qt
    ON q.query_text_id = qt.query_text_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
GROUP BY qt.query_text_id,
    q.query_id,
    p.plan_id
ORDER BY sum_total_wait_ms DESC;