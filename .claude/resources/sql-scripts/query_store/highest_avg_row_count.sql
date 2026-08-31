-- Highest average physical I/O reads
-- The number of queries that had the biggest average physical I/O reads in last 24 hours, with corresponding average row count and execution count

SELECT TOP 10 rs.avg_physical_io_reads,
    qt.query_sql_text,
    q.query_id,
    qt.query_text_id,
    p.plan_id,
    rs.runtime_stats_id,
    rsi.start_time,
    rsi.end_time,
    rs.avg_rowcount,
    rs.count_executions
FROM sys.query_store_query_text AS qt
INNER JOIN sys.query_store_query AS q
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_plan AS p
    ON q.query_id = p.query_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
INNER JOIN sys.query_store_runtime_stats_interval AS rsi
    ON rsi.runtime_stats_interval_id = rs.runtime_stats_interval_id
WHERE rsi.start_time >= DATEADD(hour, -24, GETUTCDATE())
ORDER BY rs.avg_physical_io_reads DESC;