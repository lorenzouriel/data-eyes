/* ============================================================
   Database Cleanup & Space Management
   Goal: diagnose and reduce excessive database size
   ============================================================ */

-- 1) Row count per table (ordered by number of records)
-- Useful to identify which tables actually consume space.
SELECT 
    t.[schema_id],
    t.NAME AS table_name,
    i.rows AS row_count
FROM sys.tables t
INNER JOIN sys.sysindexes i 
    ON t.object_id = i.id AND i.indid < 2
ORDER BY i.rows DESC;

---------------------------------------------------------------

-- 2) Overall database space usage
-- Shows total database size, reserved space, and unallocated space.
EXEC sp_spaceused;

---------------------------------------------------------------

-- 3) Data and log file details
-- Displays total size (SizeMB), used space (SpaceUsedMB), and free space (FreeMB).
SELECT 
    file_id,
    name,                               -- logical file name
    physical_name,                      -- physical path (.mdf / .ldf)
    type_desc,                          -- ROWS = data, LOG = log
    size * 8 / 1024 AS SizeMB,          -- total size in MB
    FILEPROPERTY(name, 'SpaceUsed') * 8 / 1024 AS SpaceUsedMB, -- used
    (size - FILEPROPERTY(name, 'SpaceUsed')) * 8 / 1024 AS FreeMB -- free
FROM sys.database_files;

---------------------------------------------------------------

-- 4) List database files
-- Confirms logical file names (needed for SHRINKFILE).
EXEC sp_helpfile;

---------------------------------------------------------------

-- 5) Shrink the main data file (MDF)
-- Replace 'myfileMDF' with the actual logical name (from sp_helpfile).
-- The number "100" is the target size in MB.
DBCC SHRINKFILE ('myfileMDF', 100);

---------------------------------------------------------------

-- 6) Shrink the log file (LDF)
-- If the database is in FULL recovery mode, run a log backup before shrinking:
-- BACKUP LOG geotracker TO DISK = 'NUL';
-- The number "50" is the target size in MB.
DBCC SHRINKFILE ('myfileMDF_log', 50);

---------------------------------------------------------------

-- 7) (Optional) Change recovery mode to SIMPLE
-- Only if point-in-time recovery is not required.
ALTER DATABASE geotracker SET RECOVERY SIMPLE;

---------------------------------------------------------------

-- 8) (Optional) Adjust auto-growth settings
-- Sets initial size to 100MB and growth increment to 50MB.
ALTER DATABASE geotracker 
MODIFY FILE ( NAME = 'myfileMDF', SIZE = 100MB, FILEGROWTH = 50MB );

ALTER DATABASE geotracker 
MODIFY FILE ( NAME = 'myfileMDF_log', SIZE = 50MB, FILEGROWTH = 25MB );