-- #######################
-- TOP 25 UNUSED INDEXES — structured/severity form
-- Purpose: Same as unused_indexes.sql, but adds a severity classification and
--          emits FOR JSON AUTO output for MCP/dashboard consumption.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> index.unused_index_update_cost
-- Caveat: sys.dm_db_index_usage_stats resets on SQL Server service restart —
--         a recently restarted instance will under-report usage. Cross-check
--         instance uptime (Overview tab / fleet_health_score) before treating
--         a CRITICAL/WARNING result here as conclusive.
-- #######################

SELECT TOP 25
    o.name AS ObjectName,
    i.name AS IndexName,
    i.index_id AS IndexID,
    dm_ius.user_seeks AS UserSeek,
    dm_ius.user_scans AS UserScans,
    dm_ius.user_lookups AS UserLookups,
    dm_ius.user_updates AS UserUpdates,
    p.TableRows,
    'DROP INDEX ' + QUOTENAME(i.name)
    + ' ON ' + QUOTENAME(s.name) + '.'
    + QUOTENAME(OBJECT_NAME(dm_ius.OBJECT_ID)) AS Drop_Statement,

    CASE
        WHEN (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) = 0
             AND dm_ius.user_updates >= 10000 THEN 'CRITICAL'
        WHEN (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) = 0
             AND dm_ius.user_updates >= 1 THEN 'WARNING'
        ELSE 'OK'
    END AS severity

FROM sys.dm_db_index_usage_stats dm_ius
INNER JOIN sys.indexes i
    ON i.index_id = dm_ius.index_id
    AND dm_ius.OBJECT_ID = i.OBJECT_ID
INNER JOIN sys.objects o
    ON dm_ius.OBJECT_ID = o.OBJECT_ID
INNER JOIN sys.schemas s
    ON o.schema_id = s.schema_id
INNER JOIN (
    SELECT
        SUM(p.rows) AS TableRows,
        p.index_id,
        p.OBJECT_ID
    FROM sys.partitions p
    GROUP BY p.index_id, p.OBJECT_ID
) p ON p.index_id = dm_ius.index_id
    AND dm_ius.OBJECT_ID = p.OBJECT_ID

WHERE OBJECTPROPERTY(dm_ius.OBJECT_ID, 'IsUserTable') = 1
    AND dm_ius.database_id = DB_ID()
    AND i.type_desc = 'nonclustered'
    AND i.is_primary_key = 0
    AND i.is_unique_constraint = 0

ORDER BY (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) ASC
FOR JSON AUTO, INCLUDE_NULL_VALUES
