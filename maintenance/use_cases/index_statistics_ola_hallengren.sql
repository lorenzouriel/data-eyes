-- #######################
-- INDEX MAINTENANCE USING OLA HALLENGREN SOLUTION
-- #######################

-- Complete Index and Statistics Maintenance
EXECUTE dbo.IndexOptimize
    @Databases = 'USER_DATABASES',                                      -- All user databases
    @FragmentationLow = NULL,                                           -- No maintenance for low fragmentation
    @FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationLevel1 = 5,                                           -- Medium fragmentation threshold
    @FragmentationLevel2 = 30,                                          -- High fragmentation threshold
    @MinNumberOfPages = 1000,                                           -- Skip small indexes
    @MaxNumberOfPages = 0,                                              -- No upper limit
    @SortInTempdb = 'Y',                                                -- Use tempdb for sort operations
    @MaxDOP = 0,                                                        -- Use server MaxDOP
    @FillFactor = 90,                                                   -- Fill factor for rebuilt indexes
    @PadIndex = 'Y',                                                    -- Apply fill factor to intermediate pages
    @LOBCompaction = 'Y',                                               -- Compact LOB pages on reorganize
    @UpdateStatistics = 'ALL',                                          -- Update statistics for indexes and columns
    @OnlyModifiedStatistics = 'Y',                                      -- Only update modified statistics
    @StatisticsModificationLevel = 10,                                   -- Percentage threshold for updating stats
    @StatisticsSample = NULL,                                           -- Auto sample
    @StatisticsResample = 'N',                                          -- Do not resample
    @PartitionLevel = 'Y',                                              -- Maintain partitioned indexes per partition
    @MSShippedObjects = 'N',                                            -- Skip system objects
    @Indexes = 'ALL_INDEXES',                                           -- All indexes
    @TimeLimit = 3600,                                                  -- Maximum execution time in seconds
    @Delay = 0,                                                         -- No delay between index commands
    @WaitAtLowPriorityMaxDuration = 30,                                  -- Max wait in minutes for online rebuild
    @WaitAtLowPriorityAbortAfterWait = 'SELF',                           -- Abort if low priority waits exceed max
    @Resumable = 'Y',                                                   -- Make online rebuilds resumable
    @AvailabilityGroups = 'ALL_AVAILABILITY_GROUPS',                    -- Check all AGs
    @LockTimeout = 0,                                                   -- No lock timeout
    @LockMessageSeverity = 16,                                          -- Error severity on lock timeouts
    @DatabasesInParallel = 'Y',                                         -- Run databases in parallel
    @ExecuteAsUser = 'dbo',                                             -- Execute as dbo
    @LogToTable = 'Y',                                                  -- Log results to dbo.CommandLog
    @Execute = 'Y';                                                     -- Execute commands


-- A. Rebuild or reorganize all indexes with fragmentation on all user databases
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30

-- B. Rebuild or reorganize all indexes with fragmentation and update modified statistics on all user databases
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@UpdateStatistics = 'ALL',
	@OnlyModifiedStatistics = 'Y'

-- C. Update statistics on all user databases
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = NULL,
	@FragmentationHigh = NULL,
	@UpdateStatistics = 'ALL'

-- D. Update modified statistics on all user databases
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = NULL,
	@FragmentationHigh = NULL,
	@UpdateStatistics = 'ALL',
	@OnlyModifiedStatistics = 'Y'

-- E. Rebuild or reorganize all indexes with fragmentation on all user databases, performing sort operations in tempdb and using all available CPUs
EXECUTE dbo.IndexOptimize @Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@SortInTempdb = 'Y',
	@MaxDOP = 0

-- F. Rebuild or reorganize all indexes with fragmentation on all user databases, using the option to maintain partitioned indexes on the partition level
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@PartitionLevel = 'Y'

-- G. Rebuild or reorganize all indexes with fragmentation on all user databases, with a time limit so that no commands are executed after 3600 seconds
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@TimeLimit = 3600

-- H. Rebuild or reorganize all indexes with fragmentation on the table Production.Product in the database AdventureWorks
EXECUTE dbo.IndexOptimize
	@Databases = 'AdventureWorks',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@Indexes = 'AdventureWorks.Production.Product'

-- I. Rebuild or reorganize all indexes with fragmentation except indexes on the table Production.Product in the database AdventureWorks
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@Indexes = 'ALL_INDEXES, -AdventureWorks.Production.Product'

-- J. Rebuild or reorganize all indexes with fragmentation on all user databases and log the results to a table
EXECUTE dbo.IndexOptimize
	@Databases = 'USER_DATABASES',
	@FragmentationLow = NULL,
	@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
	@FragmentationLevel1 = 5,
	@FragmentationLevel2 = 30,
	@LogToTable = 'Y'