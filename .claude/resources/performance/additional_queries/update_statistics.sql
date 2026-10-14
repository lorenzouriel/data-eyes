-- #######################
-- FIND DETAILS FOR STATISTICS OF WHOLE DATABASE
-- Purpose: Analyze statistics modification counters and last update dates
-- #######################

/*
Statistics Maintenance Recommendations:
01. If you have left auto update or auto create statistics on, you should not worry at all, 
    SQL Server will make the task itself.
02. If you have left auto update or auto create statistics off, you should manually update statistics
*/

-- Script 1: Modification Counter and Last Updated Statistics
SELECT DISTINCT
    OBJECT_NAME(s.[object_id]) AS TableName,
    c.name AS ColumnName,
    s.name AS StatName,
    STATS_DATE(s.[object_id], s.stats_id) AS LastUpdated,
    DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) AS DaysOld,
    dsp.modification_counter,
    s.auto_created,
    s.user_created,
    s.no_recompute,
    s.[object_id],
    s.stats_id,
    sc.stats_column_id,
    sc.column_id
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
ORDER BY DaysOld DESC;

-- Script 2: Update Statistics for Database
-- Purpose: Update all statistics in the current database
EXEC sp_updatestats;
GO

-- Check for statistics that may need updating
-- Generally consider updating when:
-- 1. DaysOld > 30 AND modification_counter > 0
-- 2. modification_counter > 1000 + (0.20 * table_row_count)

-- Update specific statistics
UPDATE STATISTICS TableName StatName;

-- Update all statistics on a table with full scan
UPDATE STATISTICS TableName WITH FULLSCAN;

-- Update with specific sample rate
UPDATE STATISTICS TableName WITH SAMPLE 50 PERCENT;
