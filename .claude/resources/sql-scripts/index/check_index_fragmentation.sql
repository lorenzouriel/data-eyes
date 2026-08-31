-- =============================================
-- QUERY: CHECK INDEX FRAGMENTATION
-- PURPOSE: Identify internal and external fragmentation of indexes in user tables
-- NOTES:
-- - Uses sys.dm_db_index_physical_stats to retrieve fragmentation and page count info
-- - Filters out HEAP tables (tables without clustered indexes)
-- - Excludes system objects (names starting with "_")
-- - Orders results by fragmentation descending to highlight the most fragmented indexes
-- =============================================

SELECT
    OBJECT_NAME(B.object_id) AS TableName,          -- Table name associated with the index
    B.name AS IndexName,                            -- Index name
    A.index_type_desc AS IndexType,                -- Type of index (CLUSTERED, NONCLUSTERED, etc.)
    A.avg_fragmentation_in_percent,               -- Average fragmentation percentage
    A.page_count                                   -- Number of pages used by the index
FROM sys.dm_db_index_physical_stats(
        DB_ID(),     -- Current database
        NULL,        -- All tables
        NULL,        -- All indexes
        NULL,        -- All partitions
        'LIMITED'    -- Limited scan mode (faster, less detailed)
    ) A
JOIN sys.indexes B ON B.object_id = A.object_id 
    AND B.index_id = A.index_id                     -- Join to get index metadata
WHERE OBJECT_NAME(B.object_id) NOT LIKE '[_]%'   -- Exclude system tables
    AND A.index_type_desc != 'HEAP'                 -- Exclude tables without clustered indexes
ORDER BY A.avg_fragmentation_in_percent DESC;    -- Show most fragmented indexes first