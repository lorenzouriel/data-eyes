-- #######################
-- INDEX FRAGMENTATION — live scan, read-only
-- Purpose: Live sys.dm_db_index_physical_stats scan (not usage-stats based like
--          .claude/resources/performance/additional_queries — this measures actual page
--          fragmentation right now). Complements missing_indexes/unused_indexes.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> index.fragmentation_pct
-- Params: @DatabaseName = NULL uses the current database (the DMV requires a
--         specific database_id); @MinFragmentationPct filters noise.
-- Caution: 'LIMITED' scan mode is used for low overhead; large databases can
--          still take time — this is not a cheap query, don't poll it too often.
-- #######################

DECLARE @DatabaseName NVARCHAR(128) = NULL;
DECLARE @MinFragmentationPct FLOAT = 5.0;

;WITH Base AS (
    SELECT TOP 50
        DB_NAME(ps.database_id) AS DatabaseName,
        OBJECT_NAME(ps.object_id, ps.database_id) AS TableName,
        i.name AS IndexName,
        ps.index_type_desc AS IndexType,
        ps.avg_fragmentation_in_percent AS FragmentationPct,
        ps.page_count AS PageCount,
        CASE
            WHEN ps.avg_fragmentation_in_percent >= 30 THEN 'CRITICAL'
            WHEN ps.avg_fragmentation_in_percent >= 5 THEN 'WARNING'
            ELSE 'OK'
        END AS severity,
        CASE
            WHEN ps.avg_fragmentation_in_percent >= 30 THEN 'REBUILD'
            WHEN ps.avg_fragmentation_in_percent >= 5 THEN 'REORGANIZE'
            ELSE 'NONE'
        END AS RecommendedAction
    FROM sys.dm_db_index_physical_stats(
            (SELECT database_id FROM sys.databases WHERE name = ISNULL(@DatabaseName, DB_NAME())),
            NULL, NULL, NULL, 'LIMITED') ps
    INNER JOIN sys.indexes i
        ON i.object_id = ps.object_id AND i.index_id = ps.index_id
    WHERE ps.avg_fragmentation_in_percent >= @MinFragmentationPct
        AND ps.page_count > 1000   -- ignore trivially small indexes
        AND ps.index_id > 0        -- exclude heaps
    ORDER BY ps.avg_fragmentation_in_percent DESC
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, FragmentationPct DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
