-- #######################
-- TOP QUERIES BY AVERAGE DURATION — structured/severity form
-- Purpose: Closes the "Top SQL" gap — this logic previously only existed as
--          inline Grafana panel SQL (monitor/dashboards/sqlserver.json) and
--          prose in monitor/docs/query_perfomance.md /
--          monitor/docs/other_metrics.md. No plain copy-paste sibling exists
--          (unlike the other performance/additional_queries/ scripts) since
--          this one was authored directly in structured form.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> query_performance.avg_duration_ms
--             (critical tier matches other_metrics.md's existing ">30s" slow-query language)
-- Params: @DatabaseName = NULL checks all databases; set it to scope to one.
-- #######################

DECLARE @DatabaseName NVARCHAR(128) = NULL;
DECLARE @TopN INT = 25;

;WITH Base AS (
    SELECT TOP (@TopN)
        DB_NAME(st.dbid) AS DatabaseName,
        qs.execution_count AS ExecutionCount,
        qs.total_elapsed_time / qs.execution_count / 1000.0 AS AvgElapsedTimeMs,
        qs.total_worker_time / qs.execution_count / 1000.0 AS AvgCpuTimeMs,
        qs.total_logical_reads / qs.execution_count AS AvgLogicalReads,
        qs.max_elapsed_time / 1000.0 AS MaxElapsedTimeMs,
        qs.last_execution_time AS LastExecutionTime,
        SUBSTRING(st.text, (qs.statement_start_offset / 2) + 1,
            ((CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset END
                - qs.statement_start_offset) / 2) + 1) AS QueryText,
        CASE
            WHEN qs.total_elapsed_time / qs.execution_count / 1000.0 >= 30000 THEN 'CRITICAL'
            WHEN qs.total_elapsed_time / qs.execution_count / 1000.0 >= 5000 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_exec_query_stats qs
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    WHERE st.dbid IS NOT NULL
        AND (@DatabaseName IS NULL OR DB_NAME(st.dbid) = @DatabaseName)
    ORDER BY AvgElapsedTimeMs DESC
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, AvgElapsedTimeMs DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
