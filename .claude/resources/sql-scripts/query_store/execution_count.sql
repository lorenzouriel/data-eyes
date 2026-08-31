-- Execution counts
-- Number of executions for each query within the last hour

SELECT q.query_id,
    qt.query_text_id,
    qt.query_sql_text,
    SUM(rs.count_executions) AS total_execution_count
FROM sys.query_store_query_text AS qt
INNER JOIN sys.query_store_query AS q
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_plan AS p
    ON q.query_id = p.query_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
GROUP BY q.query_id,
    qt.query_text_id,
    qt.query_sql_text
ORDER BY total_execution_count DESC;