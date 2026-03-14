-- #######################
-- TOP 25 UNUSED INDEXES 
-- Purpose: Identify top 25 unused nonclustered indexes
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
    -- Generate DROP INDEX statement
    'DROP INDEX ' + QUOTENAME(i.name) 
    + ' ON ' + QUOTENAME(s.name) + '.' 
    + QUOTENAME(OBJECT_NAME(dm_ius.OBJECT_ID)) AS 'drop statement'

FROM sys.dm_db_index_usage_stats dm_ius
INNER JOIN sys.indexes i 
    ON i.index_id = dm_ius.index_id 
    AND dm_ius.OBJECT_ID = i.OBJECT_ID
INNER JOIN sys.objects o 
    ON dm_ius.OBJECT_ID = o.OBJECT_ID
INNER JOIN sys.schemas s 
    ON o.schema_id = s.schema_id
INNER JOIN (
    -- Calculate table row counts per index
    SELECT 
        SUM(p.rows) AS TableRows, 
        p.index_id, 
        p.OBJECT_ID
    FROM sys.partitions p 
    GROUP BY p.index_id, p.OBJECT_ID
) p ON p.index_id = dm_ius.index_id 
    AND dm_ius.OBJECT_ID = p.OBJECT_ID

-- Filter conditions
WHERE OBJECTPROPERTY(dm_ius.OBJECT_ID, 'IsUserTable') = 1  -- Only user tables
    AND dm_ius.database_id = DB_ID()                      -- Current database only
    AND i.type_desc = 'nonclustered'                      -- Nonclustered indexes only
    AND i.is_primary_key = 0                              -- Exclude primary keys
    AND i.is_unique_constraint = 0                        -- Exclude unique constraints

-- Order by total reads (ascending = least used first)
ORDER BY (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) ASC
GO
