-- Queries with multiple plans
-- Queries with more than one plan are especially interesting, because they can be candidates for a regression in performance due to a change in plan choice.

-- The following query identifies the queries with the highest number of plans within the last hour:
SELECT q.query_id,
    object_name(object_id) AS ContainingObject,
    COUNT(*) AS QueryPlanCount,
    STRING_AGG(p.plan_id, ',') plan_ids,
    qt.query_sql_text
FROM sys.query_store_query_text AS qt
INNER JOIN sys.query_store_query AS q
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_plan AS p
    ON p.query_id = q.query_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
GROUP BY OBJECT_NAME(object_id),
    q.query_id,
    qt.query_sql_text
HAVING COUNT(DISTINCT p.plan_id) > 1
ORDER BY QueryPlanCount DESC;


-- The following query identifies these queries along with all plans within the last hour:
WITH Query_MultPlans
AS (
    SELECT COUNT(*) AS QueryPlanCount,
        q.query_id
    FROM sys.query_store_query_text AS qt
    INNER JOIN sys.query_store_query AS q
        ON qt.query_text_id = q.query_text_id
    INNER JOIN sys.query_store_plan AS p
        ON p.query_id = q.query_id
    GROUP BY q.query_id
    HAVING COUNT(DISTINCT plan_id) > 1
)
SELECT q.query_id,
    object_name(object_id) AS ContainingObject,
    query_sql_text,
    p.plan_id,
    p.query_plan AS plan_xml,
    p.last_compile_start_time,
    p.last_execution_time
FROM Query_MultPlans AS qm
INNER JOIN sys.query_store_query AS q
    ON qm.query_id = q.query_id
INNER JOIN sys.query_store_plan AS p
    ON q.query_id = p.query_id
INNER JOIN sys.query_store_query_text qt
    ON qt.query_text_id = q.query_text_id
INNER JOIN sys.query_store_runtime_stats AS rs
    ON p.plan_id = rs.plan_id
WHERE rs.last_execution_time > DATEADD(HOUR, -1, GETUTCDATE())
ORDER BY q.query_id,
    p.plan_id;