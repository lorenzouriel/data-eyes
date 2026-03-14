/* ============================================================
   BACKUP ROUTINE
   ============================================================ */

-- FULL BACKUP (Daily @ 2AM)
EXECUTE dbo.DatabaseBackup
    @Databases              = 'USER_DATABASES',
    @Directory              = 'C:\Backup',
    @BackupType             = 'FULL',
    @Verify                 = 'Y',
    @Compress               = 'Y',
    @Checksum               = 'Y',
    @CleanupTime            = 168, -- 7 days
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';


-- DIFFERENTIAL BACKUP (Every 12 hours)
EXECUTE dbo.DatabaseBackup
    @Databases              = 'USER_DATABASES',
    @Directory              = 'C:\Backup',
    @BackupType             = 'DIFF',
    @Verify                 = 'Y',
    @Compress               = 'Y',
    @Checksum               = 'Y',
    @CleanupTime            = 168, -- 7 days
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';


-- TRANSACTION LOG BACKUP (Every 15–30 minutes)
EXECUTE dbo.DatabaseBackup
    @Databases              = 'USER_DATABASES',
    @Directory              = 'C:\Backup',
    @BackupType             = 'LOG',
    @Verify                 = 'Y',
    @Compress               = 'Y',
    @Checksum               = 'Y',
    @CleanupTime            = 72,  -- 3 days log history
    @ChangeBackupType       = 'Y', -- auto convert if full/diff missing
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';


/* ============================================================
   INTEGRITY CHECKS
   ============================================================ */

-- WEEKLY (PHYSICAL_ONLY)
EXECUTE dbo.DatabaseIntegrityCheck
    @Databases              = 'USER_DATABASES',
    @CheckCommands          = 'CHECKDB',
    @PhysicalOnly           = 'Y',
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';

-- MONTHLY (Full deep CHECKDB)
EXECUTE dbo.DatabaseIntegrityCheck
    @Databases              = 'USER_DATABASES',
    @CheckCommands          = 'CHECKDB',
    @PhysicalOnly           = 'N',
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';


/* ============================================================
   INDEX MAINTENANCE
   ============================================================ */

-- WEEKLY (Reorganize/Rebuild depending on fragmentation)
EXECUTE dbo.IndexOptimize
    @Databases              = 'USER_DATABASES',
    @FragmentationLow       = NULL,
    @FragmentationMedium    = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationHigh      = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationLevel1    = 5,
    @FragmentationLevel2    = 30,
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';


-- WEEKLY (Update all statistics)
EXECUTE dbo.IndexOptimize
    @Databases              = 'USER_DATABASES',
    @FragmentationLow       = NULL,
    @FragmentationMedium    = NULL,
    @FragmentationHigh      = NULL,
    @UpdateStatistics       = 'ALL',
    @OnlyModifiedStatistics = 'Y', -- avoid unnecessary updates
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';
