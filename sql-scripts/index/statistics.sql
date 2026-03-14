/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Last Modified: 2025-08-19
-- Purpose:      Compute table/index usage statistics in SQL Server
-- Description:  This query reports operational statistics per table/index using the DMV
--               sys.dm_db_index_operational_stats. The statistics help identify which
--               indexes are heavily scanned, updated, inserted, deleted, or looked up.
--               
--               Fields include:
--                 Table_Name      : Name of the user table
--                 Index_Name      : Name of the index on the table
--                 Partition       : Partition number of the index (for partitioned tables)
--                 Index_ID        : ID of the index (1 = clustered, 0 = heap, >1 = nonclustered)
--                 Index_Type      : Type of index (CLUSTERED, NONCLUSTERED, HEAP)
--                 Percent_Update  : Ratio of updates to total operations (updates + inserts + deletes + scans + lookups + merges)
--                 Percent_Insert  : Ratio of inserts to total operations
--                 Percent_Delete  : Ratio of deletes to total operations
--                 Percent_Scan    : Ratio of scans to total operations
--                 Percent_Lookup  : Ratio of singleton lookups to total operations
************************************************************************************************/

-- ============================================================
-- Query: Compute Index Operational Percentages (U, S, Insert, Delete, Lookup)
-- ============================================================

SELECT 
    o.name AS [Table_Name],                     -- User table name
    x.name AS [Index_Name],                     -- Index name on the table
    i.partition_number AS [Partition],          -- Partition number of the index
    i.index_id AS [Index_ID],                   -- Index ID (0 = Heap, 1 = Clustered, >1 = Nonclustered)
    x.type_desc AS [Index_Type],                -- Type of index
    i.leaf_update_count * 100.0 /               -- Percent of total operations that are updates
        NULLIF((i.range_scan_count 
                 + i.leaf_insert_count
                 + i.leaf_delete_count 
                 + i.leaf_update_count
                 + i.leaf_page_merge_count 
                 + i.singleton_lookup_count),0) AS [Percent_Update],
    i.leaf_insert_count * 100.0 /               -- Percent of total operations that are inserts
        NULLIF((i.range_scan_count 
                 + i.leaf_insert_count
                 + i.leaf_delete_count 
                 + i.leaf_update_count
                 + i.leaf_page_merge_count 
                 + i.singleton_lookup_count),0) AS [Percent_Insert],
    i.leaf_delete_count * 100.0 /               -- Percent of total operations that are deletes
        NULLIF((i.range_scan_count 
                 + i.leaf_insert_count
                 + i.leaf_delete_count 
                 + i.leaf_update_count
                 + i.leaf_page_merge_count 
                 + i.singleton_lookup_count),0) AS [Percent_Delete],
    i.range_scan_count * 100.0 /                -- Percent of total operations that are range scans
        NULLIF((i.range_scan_count 
                 + i.leaf_insert_count
                 + i.leaf_delete_count 
                 + i.leaf_update_count
                 + i.leaf_page_merge_count 
                 + i.singleton_lookup_count),0) AS [Percent_Scan],
    i.singleton_lookup_count * 100.0 /          -- Percent of total operations that are singleton lookups
        NULLIF((i.range_scan_count 
                 + i.leaf_insert_count
                 + i.leaf_delete_count 
                 + i.leaf_update_count
                 + i.leaf_page_merge_count 
                 + i.singleton_lookup_count),0) AS [Percent_Lookup]
FROM sys.dm_db_index_operational_stats (DB_ID(), NULL, NULL, NULL) i
JOIN sys.objects o 
    ON o.object_id = i.object_id
JOIN sys.indexes x 
    ON x.object_id = i.object_id AND x.index_id = i.index_id
WHERE (i.range_scan_count 
       + i.leaf_insert_count
       + i.leaf_delete_count 
       + i.leaf_update_count
       + i.leaf_page_merge_count 
       + i.singleton_lookup_count) != 0   -- Only include indexes with activity
AND OBJECTPROPERTY(i.object_id,'IsUserTable') = 1 -- Only user tables
ORDER BY [Percent_Update] DESC, [Percent_Scan] DESC;