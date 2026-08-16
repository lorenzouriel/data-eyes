-- #######################
-- STATISTICS STALENESS — structured/severity form
-- Purpose: Same analysis as update_statistics.sql's Script 1, but adds a
--          severity classification and emits FOR JSON AUTO output for
--          MCP/dashboard consumption. (Script 2 in the original — sp_updatestats
--          — is a write operation and has no structured/read-only equivalent
--          here; run it via the original update_statistics.sql or maintenance/.)
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> index.stats_staleness_days
-- #######################

SELECT DISTINCT
    OBJECT_NAME(s.[object_id]) AS TableName,
    c.name AS ColumnName,
    s.name AS StatName,
    STATS_DATE(s.[object_id], s.stats_id) AS LastUpdated,
    DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) AS DaysOld,
    dsp.modification_counter AS ModificationCounter,
    s.auto_created AS AutoCreated,
    s.user_created AS UserCreated,
    s.no_recompute AS NoRecompute,

    CASE
        WHEN DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) >= 60
             AND dsp.modification_counter >= 1000 THEN 'CRITICAL'
        WHEN DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) >= 30
             AND dsp.modification_counter >= 1 THEN 'WARNING'
        ELSE 'OK'
    END AS severity

FROM sys.stats s
JOIN sys.stats_columns sc
    ON sc.[object_id] = s.[object_id]
    AND sc.stats_id = s.stats_id
JOIN sys.columns c
    ON c.[object_id] = sc.[object_id]
    AND c.column_id = sc.column_id
JOIN sys.partitions par
    ON par.[object_id] = s.[object_id]
JOIN sys.objects obj
    ON par.[object_id] = obj.[object_id]
CROSS APPLY sys.dm_db_stats_properties(sc.[object_id], s.stats_id) AS dsp
WHERE OBJECTPROPERTY(s.OBJECT_ID, 'IsUserTable') = 1
    AND (s.auto_created = 1 OR s.user_created = 1)
ORDER BY DaysOld DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
