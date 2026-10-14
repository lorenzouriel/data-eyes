----------------------------------------------------------
-- SECTION: Index Optimization Using dbo.IndexOptimize
----------------------------------------------------------
-- Description:
-- Executes the IndexOptimize stored procedure (from Ola Hallengren's Maintenance Solution)
-- to reorganize or rebuild indexes and update statistics for the specified database.
-- Helps improve performance by reducing fragmentation and keeping statistics up-to-date.

USE [master];
GO

EXECUTE [dbo].[IndexOptimize] 
    @Databases = 'database',                         -- Target database for maintenance
    @FragmentationLow = NULL,                        -- No action on low fragmentation
    @FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',  
                                                    -- Actions for medium fragmentation indexes
    @FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE', 
                                                    -- Actions for high fragmentation indexes
    @FragmentationLevel1 = 5,                        -- Threshold (%) for low fragmentation
    @FragmentationLevel2 = 30,                       -- Threshold (%) for medium fragmentation
    @PageCountLevel = 1,                             -- Minimum number of pages to consider an index
    @WaitAtLowPriorityMaxDuration = 1,               -- Max duration (minutes) to wait when rebuilding at low priority
    @WaitAtLowPriorityAbortAfterWait = 'NONE',       -- Behavior if wait exceeds max duration (NONE = do not abort)
    @UpdateStatistics = 'ALL',                       -- Update all statistics
    @OnlyModifiedStatistics = 'Y',                   -- Only update statistics if they have changed
    @LogToTable = 'Y';                               -- Log results into the maintenance table