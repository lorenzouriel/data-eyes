-- #######################
-- DBCC CHECKDB USING OLA HALLENGREN SOLUTION
-- #######################

-- Complete Integrity Check
EXECUTE dbo.DatabaseIntegrityCheck
    @Databases = 'USER_DATABASES',                   -- All user databases
    @CheckCommands = 'CHECKDB,CHECKALLOC,CHECKCATALOG', -- Full check of DB, allocation, catalog
    @PhysicalOnly = 'N',                             -- Include logical checks
    @DataPurity = 'Y',                               -- Check column values for validity
    @NoIndex = 'N',                                  -- Include nonclustered indexes
    @ExtendedLogicalChecks = 'Y',                    -- Enable extended logical checks
    @NoInformationalMessages = 'Y',                  -- Suppress informational messages
    @TabLock = 'N',                                  -- Use snapshot instead of table locks
    @MaxDOP = 0,                                     -- Use default MaxDOP
    @AvailabilityGroups = 'ALL_AVAILABILITY_GROUPS', -- Check all AGs
    @AvailabilityGroupReplicas = 'ALL',              -- Check all replicas
    @Updateability = 'ALL',                           -- Check read/write and read-only DBs
    @TimeLimit = 0,                                  -- No time limit
    @LockTimeout = 0,                                -- No lock timeout
    @LogToTable = 'Y',                               -- Log results to dbo.CommandLog
    @DatabasesInParallel = 'Y',                      -- Run databases in parallel
    @Execute = 'Y';                                  -- Execute (not just print)


-- A. Check the integrity of all user databases
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKDB'

-- B. Check the physical integrity of all user databases
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKDB',
	@PhysicalOnly = 'Y'

-- C. Check the integrity of all user databases, using the option not to check nonclustered indexes
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKDB',
	@NoIndex = 'Y'

-- D. Check the integrity of all user databases, using the option to perform extended logical checks
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKDB',
	@ExtendedLogicalChecks = 'Y'

-- E. Check the integrity of the filegroup PRIMARY in the database AdventureWorks
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'AdventureWorks',
	@CheckCommands = 'CHECKFILEGROUP',
	@FileGroups = 'AdventureWorks.PRIMARY'

-- F. Check the integrity of all filegroups except the filegroup PRIMARY in the database AdventureWorks
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKFILEGROUP',
	@FileGroups = 'ALL_FILEGROUPS, -AdventureWorks.PRIMARY'

-- G. Check the integrity of the table Production.Product in the database AdventureWorks
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'AdventureWorks',
	@CheckCommands = 'CHECKTABLE',
	@Objects = 'AdventureWorks.Production.Product'

-- H. Check the integrity of all tables except the table Production.Product in the database AdventureWorks
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKTABLE',
	@Objects = 'ALL_OBJECTS, -AdventureWorks.Production.Product'

-- I. Check the disk-space allocation structures of all user databases
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKALLOC'

-- J. Check the catalog consistency of all user databases
EXECUTE dbo.DatabaseIntegrityCheck
	@Databases = 'USER_DATABASES',
	@CheckCommands = 'CHECKCATALOG'