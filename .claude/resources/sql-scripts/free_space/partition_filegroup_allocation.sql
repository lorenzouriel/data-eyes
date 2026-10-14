/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Examine partition and filegroup allocation, check file free space, 
--               rebuild partitions with compression, and shrink files if needed.
-- Description:  Multiple scripts for partition and file management:
--               1. View partition info and filegroup
--               2. Check free space per data file
--               3. Rebuild a partition with PAGE compression
--               4. Shrink a database file
--               5. Verify compression settings per partition
************************************************************************************************/

-- ============================================================
-- 1. View partitions and associated filegroups for a table
-- ============================================================
SELECT DISTINCT
    OBJECT_NAME(p.object_id) AS Table_Name,      -- Table name
    f.name AS Filegroup_Name,                    -- Filegroup storing the partition
    p.partition_number,                          -- Partition number
    p.rows                                       -- Number of rows in the partition
FROM sys.system_internals_allocation_units a
JOIN sys.partitions p 
    ON p.partition_id = a.container_id
JOIN sys.filegroups f 
    ON a.data_space_id = f.data_space_id        -- Correct join for filegroup ID
WHERE p.object_id = OBJECT_ID(N'dim.table')     -- Replace with your table name
ORDER BY p.partition_number;
GO

-- ============================================================
-- 2. Check free space per data file
-- ============================================================
SELECT 
    DB_NAME() AS DbName,
    name AS FileName,
    size/128.0 AS CurrentSizeMB,                -- Size of file in MB
    size/128.0 - CAST(FILEPROPERTY(name, 'SpaceUsed') AS INT)/128.0 AS FreeSpaceMB  -- Free space in MB
FROM sys.database_files
WHERE type_desc = 'ROWS'                        -- Only rowstore data files
  AND name LIKE 'FGY%';                         -- Filter by file name pattern
GO

-- ============================================================
-- 3. Rebuild a single partition with PAGE compression
-- ============================================================
DECLARE
    @AlterSQL NVARCHAR(MAX),
    @PartitionNumber INT = 7;                   -- Set the partition number to rebuild

-- Replace [table] with your actual table name
SET @AlterSQL = N'ALTER TABLE [table] REBUILD PARTITION = ' + CAST(@PartitionNumber AS NVARCHAR(10)) + '
WITH (DATA_COMPRESSION = PAGE);';

PRINT @AlterSQL;                                 -- Optional: review generated SQL
EXEC sp_executesql @AlterSQL;
GO

-- ============================================================
-- 4. Shrink a database file
-- ============================================================
DECLARE
    @ShrinkSQL NVARCHAR(MAX),
    @FileName SYSNAME = N'FGM11_5099EF98';      -- Replace with your actual file name

SET @ShrinkSQL = N'DBCC SHRINKFILE (' + QUOTENAME(@FileName) + ');';

PRINT @ShrinkSQL;                               -- Optional: review generated SQL
EXEC sp_executesql @ShrinkSQL;
GO

-- ============================================================
-- 5. Check compression settings per partition
-- ============================================================
SELECT
    partition_number,
    data_compression,
    data_compression_desc
FROM sys.partitions
WHERE object_id = OBJECT_ID('[table]');        -- Replace with your table name
GO