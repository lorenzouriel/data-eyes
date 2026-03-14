/* ============================================================
   SQL Server Agent Jobs for Ola Hallengren's Maintenance
   ============================================================
   NOTE: Requires Ola Hallengren's scripts already installed:
   - DatabaseBackup
   - DatabaseIntegrityCheck
   - IndexOptimize
   ============================================================ */

USE msdb;
GO

/* ============================================================
   1. FULL BACKUP (Daily @ 2AM)
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'Backup FULL - Daily 2AM';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'Backup FULL - Daily 2AM',
    @step_name = N'Backup FULL',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.DatabaseBackup
    @Databases              = ''USER_DATABASES'',
    @Directory              = ''C:\Backup'',
    @BackupType             = ''FULL'',
    @Verify                 = ''Y'',
    @Compress               = ''Y'',
    @Checksum               = ''Y'',
    @CleanupTime            = 168,
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Daily 2AM',
    @freq_type = 4,            -- daily
    @freq_interval = 1,
    @active_start_time = 020000; -- 02:00 AM

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'Backup FULL - Daily 2AM',
    @schedule_name = N'Daily 2AM';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'Backup FULL - Daily 2AM';


/* ============================================================
   2. DIFFERENTIAL BACKUP (Every 12h)
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'Backup DIFF - Every 12h';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'Backup DIFF - Every 12h',
    @step_name = N'Backup DIFF',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.DatabaseBackup
    @Databases              = ''USER_DATABASES'',
    @Directory              = ''C:\Backup'',
    @BackupType             = ''DIFF'',
    @Verify                 = ''Y'',
    @Compress               = ''Y'',
    @Checksum               = ''Y'',
    @CleanupTime            = 168,
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Every 12h',
    @freq_type = 4,             -- daily
    @freq_interval = 1,
    @freq_subday_type = 8,      -- hours
    @freq_subday_interval = 12, -- every 12h
    @active_start_time = 060000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'Backup DIFF - Every 12h',
    @schedule_name = N'Every 12h';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'Backup DIFF - Every 12h';


/* ============================================================
   3. LOG BACKUP (Every 30 min)
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'Backup LOG - Every 30 min';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'Backup LOG - Every 30 min',
    @step_name = N'Backup LOG',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.DatabaseBackup
    @Databases              = ''USER_DATABASES'',
    @Directory              = ''C:\Backup'',
    @BackupType             = ''LOG'',
    @Verify                 = ''Y'',
    @Compress               = ''Y'',
    @Checksum               = ''Y'',
    @CleanupTime            = 72,
    @ChangeBackupType       = ''Y'',
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Every 30 min',
    @freq_type = 4,               -- daily
    @freq_interval = 1,
    @freq_subday_type = 4,        -- minutes
    @freq_subday_interval = 30,   -- every 30 min
    @active_start_time = 000000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'Backup LOG - Every 30 min',
    @schedule_name = N'Every 30 min';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'Backup LOG - Every 30 min';


/* ============================================================
   4. WEEKLY CHECKDB (PHYSICAL_ONLY) - Sunday 3AM
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'CHECKDB Weekly PHYSICAL_ONLY';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'CHECKDB Weekly PHYSICAL_ONLY',
    @step_name = N'Integrity Check',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.DatabaseIntegrityCheck
    @Databases              = ''USER_DATABASES'',
    @CheckCommands          = ''CHECKDB'',
    @PhysicalOnly           = ''Y'',
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Weekly Sunday 3AM',
    @freq_type = 8,             -- weekly
    @freq_interval = 1,         -- Sunday
	@freq_recurrence_factor = 1, -- every week
    @active_start_time = 030000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'CHECKDB Weekly PHYSICAL_ONLY',
    @schedule_name = N'Weekly Sunday 3AM';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'CHECKDB Weekly PHYSICAL_ONLY';


/* ============================================================
   5. MONTHLY CHECKDB (Full) - 1st Sunday 3AM
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'CHECKDB Monthly Full';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'CHECKDB Monthly Full',
    @step_name = N'Integrity Check',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.DatabaseIntegrityCheck
    @Databases              = ''USER_DATABASES'',
    @CheckCommands          = ''CHECKDB'',
    @PhysicalOnly           = ''N'',
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'First Sunday 3AM',
    @freq_type = 16,            -- monthly relative
    @freq_interval = 1,         -- Sunday
    @freq_relative_interval = 1,-- First
	@freq_recurrence_factor = 1,  -- every month
    @active_start_time = 030000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'CHECKDB Monthly Full',
    @schedule_name = N'First Sunday 3AM';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'CHECKDB Monthly Full';


/* ============================================================
   6. INDEX MAINTENANCE - Weekly Saturday 1AM
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'IndexOptimize Weekly';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'IndexOptimize Weekly',
    @step_name = N'Index Maintenance',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.IndexOptimize
    @Databases              = ''USER_DATABASES'',
    @FragmentationLow       = NULL,
    @FragmentationMedium    = ''INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE'',
    @FragmentationHigh      = ''INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE'',
    @FragmentationLevel1    = 5,
    @FragmentationLevel2    = 30,
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Weekly Saturday 1AM',
    @freq_type = 8,            -- weekly
    @freq_interval = 64,       -- Saturday
	@freq_recurrence_factor = 1, -- every week
    @active_start_time = 010000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'IndexOptimize Weekly',
    @schedule_name = N'Weekly Saturday 1AM';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'IndexOptimize Weekly';


/* ============================================================
   7. STATISTICS UPDATE - Weekly Saturday 4AM
   ============================================================ */
EXEC msdb.dbo.sp_add_job
    @job_name = N'Statistics Update Weekly';

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'Statistics Update Weekly',
    @step_name = N'Update Statistics',
    @subsystem = N'TSQL',
    @command = N'
EXECUTE dbo.IndexOptimize
    @Databases              = ''USER_DATABASES'',
    @FragmentationLow       = NULL,
    @FragmentationMedium    = NULL,
    @FragmentationHigh      = NULL,
    @UpdateStatistics       = ''ALL'',
    @OnlyModifiedStatistics = ''Y'',
    @LogToTable             = ''Y'',
    @DatabasesInParallel    = ''Y'';',
    @database_name = N'master';

EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Weekly Saturday 4AM',
    @freq_type = 8,            -- weekly
    @freq_interval = 64,       -- Saturday
	@freq_recurrence_factor = 1, -- every week
    @active_start_time = 040000;

EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'Statistics Update Weekly',
    @schedule_name = N'Weekly Saturday 4AM';

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'Statistics Update Weekly';