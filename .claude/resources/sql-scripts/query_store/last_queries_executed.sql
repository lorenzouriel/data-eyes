-- Last queries executed on the database
-- The last n queries executed on the database within the last hour

SELECT TOP 10 qt.query_sql_text,
    q.query_id,
    qt.query_text_id,
    p.plan_id,
    rs.last_execution_time
FROM sys.query_store_query_text AS qt
INNER JOIN sys.query_store_query AS q
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_plan AS p
    ON q.query_id = p.query_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
ORDER BY rs.last_execution_time DESC;