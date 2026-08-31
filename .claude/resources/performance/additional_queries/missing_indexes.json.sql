-- #######################
-- TOP 25 MISSING INDEXES BY ESTIMATED IMPACT — structured/severity form
-- Purpose: Same as missing_indexes.sql, but adds a severity classification and
--          emits FOR JSON AUTO output for MCP/dashboard consumption.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> index.missing_index_impact_score
--             (heuristic — no documented industry-standard value, tune per workload)
-- #######################

SELECT TOP 25
    dm_mid.database_id AS DatabaseID,
    dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) AS Avg_Estimated_Impact,
    dm_migs.last_user_seek AS Last_User_Seek,
    OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) AS TableName,

    -- Generate CREATE INDEX statement
    'CREATE INDEX [IX_' + OBJECT_NAME(dm_mid.OBJECT_ID, dm_mid.database_id) + '_'
    + REPLACE(REPLACE(REPLACE(ISNULL(dm_mid.equality_columns,''), ', ', '_'), '[', ''), ']', '')
    + CASE
        WHEN dm_mid.equality_columns IS NOT NULL
        AND dm_mid.inequality_columns IS NOT NULL THEN '_'
        ELSE ''
      END
    + REPLACE(REPLACE(REPLACE(ISNULL(dm_mid.inequality_columns,''), ', ', '_'), '[', ''), ']', '')
    + ']'
    + ' ON ' + dm_mid.statement
    + ' (' + ISNULL(dm_mid.equality_columns,'')
    + CASE
        WHEN dm_mid.equality_columns IS NOT NULL
        AND dm_mid.inequality_columns IS NOT NULL THEN ','
        ELSE ''
      END
    + ISNULL(dm_mid.inequality_columns, '')
    + ')'
    + ISNULL(' INCLUDE (' + dm_mid.included_columns + ')', '') AS Create_Statement,

    CASE
        WHEN dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) >= 100000 THEN 'CRITICAL'
        WHEN dm_migs.avg_user_impact * (dm_migs.user_seeks + dm_migs.user_scans) >= 10000 THEN 'WARNING'
        ELSE 'OK'
    END AS severity

FROM sys.dm_db_missing_index_groups dm_mig
INNER JOIN sys.dm_db_missing_index_group_stats dm_migs
    ON dm_migs.group_handle = dm_mig.index_group_handle
INNER JOIN sys.dm_db_missing_index_details dm_mid
    ON dm_mig.index_handle = dm_mid.index_handle

-- Filter for current database only
WHERE dm_mid.database_ID = DB_ID()

ORDER BY Avg_Estimated_Impact DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
