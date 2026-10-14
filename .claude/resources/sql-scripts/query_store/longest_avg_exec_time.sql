-- Longest average execution time
-- The number of queries with the highest average duration within last hour

SELECT TOP 10 ROUND(CONVERT(FLOAT, SUM(rs.avg_duration * rs.count_executions)) /
        NULLIF(SUM(rs.count_executions), 0), 2) avg_duration,
    SUM(rs.count_executions) AS total_execution_count,
    qt.query_sql_text,
    q.query_id,
    qt.query_text_id,
    p.plan_id,
    GETUTCDATE() AS CurrentUTCTime,
    MAX(rs.last_execution_time) AS last_execution_time
FROM sys.query_store_query_text AS qt
INNER JOIN sys.query_store_query AS q
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_plan AS p
    ON q.query_id = p.query_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
GROUP BY qt.query_sql_text,
    q.query_id,
    qt.query_text_id,
    p.plan_id
ORDER BY avg_duration DESC;