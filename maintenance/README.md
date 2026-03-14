# Maintenance

A comprehensive, production-ready database maintenance automation solution for Microsoft SQL Server built on Ola Hallengren's industry-standard maintenance scripts. This solution provides automated backups, integrity checks, and index optimization through SQL Server Agent jobs.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Maintenance Tasks](#maintenance-tasks)
- [Scheduling](#scheduling)
- [Configuration](#configuration)
- [Monitoring and Logging](#monitoring-and-logging)
- [Use Cases](#use-cases)
- [Best Practices](#best-practices)

## Overview

This maintenance solution delivers automated operational tasks for SQL Server databases, ensuring:

- **Data Protection** - Automated full, differential, and transaction log backups
- **Data Integrity** - Regular CHECKDB operations to detect corruption
- **Performance Optimization** - Index defragmentation and statistics updates
- **Operational Excellence** - Comprehensive logging and automated cleanup

### Key Benefits

- Zero external dependencies (SQL Server Agent only)
- Industry-proven maintenance procedures by Ola Hallengren
- Flexible scheduling with 7 pre-configured jobs
- Comprehensive logging to database tables
- Production-tested and widely adopted

### Role in Data Eyes Project

The maintenance solution is the **automation component** of the Data Eyes ecosystem:

1. **Monitoring** ([monitor/](../monitor/)) - Grafana/Prometheus dashboards for visibility
2. **Performance** ([performance/](../performance/)) - Analysis and tuning guidance
3. **Maintenance** (this solution) - Automated operational tasks

Together, these provide complete SQL Server observability and automation.

## Features

### Backup Management

- ✓ Daily full database backups with compression
- ✓ Differential backups every 12 hours
- ✓ Transaction log backups every 30 minutes
- ✓ Automated backup verification with checksums
- ✓ Automatic cleanup of old backups (7-day retention)
- ✓ Parallel backup execution for multiple databases

### Database Integrity

- ✓ Weekly fast integrity checks (PHYSICAL_ONLY)
- ✓ Monthly comprehensive integrity checks
- ✓ DBCC CHECKDB, CHECKALLOC, CHECKCATALOG
- ✓ Corruption detection and alerting

### Index Optimization

- ✓ Weekly index defragmentation
- ✓ Intelligent rebuild/reorganize based on fragmentation levels
- ✓ Statistics updates on modified objects
- ✓ Online and resumable operations support
- ✓ Parallel execution with MaxDOP control

### Operational Features

- ✓ SQL Server Agent job scheduling
- ✓ Comprehensive logging to CommandLog table
- ✓ Email notifications (SQL Agent alerts)
- ✓ No third-party software required
- ✓ Support for Azure, AWS, and network share backups

## Prerequisites

### SQL Server Requirements

- **SQL Server Version:** 2012 or higher (2016+ recommended)
- **SQL Server Agent:** Must be running and enabled
- **Edition:** Standard or Enterprise (some features require Enterprise)
- **Permissions:** sysadmin role or equivalent

### Ola Hallengren Scripts

**CRITICAL:** This solution requires Ola Hallengren's maintenance scripts to be installed first.

**Download:** [https://ola.hallengren.com/](https://ola.hallengren.com/)

**Required Stored Procedures:**
- `master.dbo.DatabaseBackup` - Backup operations
- `master.dbo.DatabaseIntegrityCheck` - Integrity validation
- `master.dbo.IndexOptimize` - Index and statistics maintenance

### Storage Requirements

- **Backup Directory:** `C:\Backup` (configurable)
- **Disk Space:** Sufficient for full backups + differential + logs
- **Estimate:** 1.5x total database size minimum
- **Network Access:** If using network shares or cloud storage

### Permissions

```sql
-- Grant required permissions to SQL Agent service account
GRANT EXECUTE ON master.dbo.DatabaseBackup TO [ServiceAccount];
GRANT EXECUTE ON master.dbo.DatabaseIntegrityCheck TO [ServiceAccount];
GRANT EXECUTE ON master.dbo.IndexOptimize TO [ServiceAccount];

-- Or use sysadmin role (recommended for maintenance)
ALTER SERVER ROLE sysadmin ADD MEMBER [ServiceAccount];
```

## Quick Start

### Step 1: Install Ola Hallengren Scripts

1. Download MaintenanceSolution.sql from [https://ola.hallengren.com/](https://ola.hallengren.com/)
2. Review the script and configuration options
3. Execute in SQL Server Management Studio (SSMS) against master database
4. Verify procedures exist:

```sql
SELECT name FROM master.sys.procedures
WHERE name IN ('DatabaseBackup', 'DatabaseIntegrityCheck', 'IndexOptimize');
```

### Step 2: Create Backup Directory

```bash
# Windows Command Prompt
mkdir C:\Backup

# PowerShell
New-Item -Path "C:\Backup" -ItemType Directory

# Or use custom path and update playbook.sql
```

### Step 3: Configure Maintenance Playbook

Edit [playbook.sql](playbook.sql) and adjust parameters:

```sql
-- Backup location (line 8, 21, 34)
@Directory = N'C:\Backup',  -- Change to your backup path

-- Retention period (line 13, 26, 39)
@CleanupTime = 168,  -- 168 hours = 7 days (adjust as needed)
```

### Step 4: Deploy SQL Agent Jobs

Execute [sql_agent_schedule_playbook.sql](sql_agent_schedule_playbook.sql) in SSMS:

```sql
-- This will create 7 SQL Agent jobs with schedules
-- Review each job in SQL Server Agent → Jobs
```

### Step 5: Verify Jobs

1. Open SSMS → SQL Server Agent → Jobs
2. Verify 7 jobs are created and enabled
3. Check job schedules match requirements
4. Optionally run a test job:

```sql
EXEC msdb.dbo.sp_start_job @job_name = 'Backup FULL - Daily 2AM';
```

### Step 6: Monitor Execution

```sql
-- View recent maintenance operations
SELECT TOP 100
    DatabaseName,
    CommandType,
    StartTime,
    EndTime,
    DATEDIFF(SECOND, StartTime, EndTime) AS DurationSeconds,
    ErrorMessage
FROM master.dbo.CommandLog
ORDER BY StartTime DESC;
```

## Architecture

### Component Diagram

```bash
┌─────────────────────────────────────────────────────┐
│           SQL Server Maintenance Solution           │
└─────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼───┐       ┌───▼───┐       ┌───▼────┐
    │Backups│       │Integrity│      │Index   │
    │       │       │Checks │       │Optimize│
    └───┬───┘       └───┬───┘       └───┬────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                   ┌────▼─────┐
                   │SQL Agent │
                   │  Jobs    │
                   └────┬─────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
    ┌───▼────┐    ┌────▼─────┐    ┌───▼────┐
    │ Backup │    │CommandLog│    │ Email  │
    │  Files │    │  Table   │    │ Alerts │
    └────────┘    └──────────┘    └────────┘
```

### File Structure

```bash
maintenance/
├── playbook.sql                              # Core maintenance routines (92 lines)
├── sql_agent_schedule_playbook.sql           # SQL Agent job definitions (269 lines)
└── use_cases/
    ├── backup_ola_hallengren.sql             # 15 backup examples (157 lines)
    ├── dbcc_check_ola_hallengren.sql         # 10 integrity check examples (81 lines)
    └── index_statistics_ola_hallengren.sql   # Index maintenance examples (137 lines)
```

## Maintenance Tasks

### 1. Backup Operations

Located in [playbook.sql](playbook.sql) - Lines 1-47

#### Full Backup (Daily @ 2 AM)

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases = 'USER_DATABASES',
    @Directory = N'C:\Backup',
    @BackupType = 'FULL',
    @Verify = 'Y',              -- Verify backup integrity
    @Compress = 'Y',            -- Compress backup files
    @CheckSum = 'Y',            -- Calculate checksums
    @CleanupTime = 168,         -- Delete backups older than 7 days
    @LogToTable = 'Y',          -- Log to CommandLog table
    @DatabasesInParallel = 'Y'; -- Process multiple DBs simultaneously
```

**Features:**
- Backs up all user databases
- 50-60% compression ratio
- Verification ensures recoverability
- 7-day retention policy
- Parallel execution for speed

#### Differential Backup (Every 12 Hours)

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases = 'USER_DATABASES',
    @Directory = N'C:\Backup',
    @BackupType = 'DIFF',
    @Verify = 'Y',
    @Compress = 'Y',
    @CheckSum = 'Y',
    @CleanupTime = 168;
```

**Features:**
- Captures changes since last full backup
- Faster than full backups
- Reduces recovery time
- Same 7-day retention

#### Transaction Log Backup (Every 30 Minutes)

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases = 'USER_DATABASES',
    @Directory = N'C:\Backup',
    @BackupType = 'LOG',
    @Verify = 'Y',
    @Compress = 'Y',
    @CheckSum = 'Y',
    @CleanupTime = 72,          -- 3-day retention for logs
    @ChangeBackupType = 'Y';    -- Auto-convert if full/diff missing
```

**Features:**
- Point-in-time recovery capability
- 30-minute RPO (Recovery Point Objective)
- 3-day retention (logs age faster)
- Auto-fallback to full backup if needed

### 2. Integrity Checks

Located in [playbook.sql](playbook.sql) - Lines 49-67

#### Weekly Fast Check (Sunday @ 3 AM)

```sql
EXECUTE master.dbo.DatabaseIntegrityCheck
    @Databases = 'USER_DATABASES',
    @CheckCommands = 'CHECKDB',
    @PhysicalOnly = 'Y',        -- Physical structure only (faster)
    @LogToTable = 'Y',
    @DatabasesInParallel = 'Y';
```

**Purpose:**
- Detect physical corruption quickly
- Low resource impact
- Runs weekly to catch issues early
- ~30-40% faster than full check

#### Monthly Deep Check (1st Sunday @ 3 AM)

```sql
EXECUTE master.dbo.DatabaseIntegrityCheck
    @Databases = 'USER_DATABASES',
    @CheckCommands = 'CHECKDB',
    @LogToTable = 'Y',
    @DatabasesInParallel = 'Y';
```

**Purpose:**
- Complete logical and physical validation
- Checks all indexes, tables, catalogs
- Comprehensive corruption detection
- Thorough but resource-intensive

### 3. Index Optimization

Located in [playbook.sql](playbook.sql) - Lines 69-92

#### Weekly Index Maintenance (Saturday @ 1 AM)

```sql
EXECUTE master.dbo.IndexOptimize
    @Databases = 'USER_DATABASES',
    @FragmentationLow = NULL,                    -- Don't touch low fragmentation
    @FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationLevel1 = 5,                    -- Medium threshold: 5%
    @FragmentationLevel2 = 30,                   -- High threshold: 30%
    @UpdateStatistics = 'ALL',
    @OnlyModifiedStatistics = 'Y',
    @LogToTable = 'Y';
```

**Strategy:**
- **< 5% fragmentation:** No action (minimal performance impact)
- **5-30% fragmentation:** REORGANIZE first, fallback to REBUILD
- **> 30% fragmentation:** REBUILD (online if possible)
- Online operations minimize downtime

#### Weekly Statistics Update (Saturday @ 4 AM)

```sql
EXECUTE master.dbo.IndexOptimize
    @Databases = 'USER_DATABASES',
    @FragmentationLow = NULL,
    @FragmentationMedium = NULL,
    @FragmentationHigh = NULL,
    @UpdateStatistics = 'ALL',
    @OnlyModifiedStatistics = 'Y',               -- Skip unmodified stats
    @LogToTable = 'Y';
```

**Purpose:**
- Updates query optimizer statistics
- Only touches modified statistics (efficient)
- Improves execution plan quality
- Runs after index maintenance completes

## Scheduling

### Job Schedule Matrix

```bash
┌──────────────────────────────────────────────────────────────┐
│ Time  │ Sunday          │ Monday-Friday   │ Saturday          │
├───────┼─────────────────┼─────────────────┼───────────────────┤
│ 01:00 │                 │                 │ IndexOptimize     │
│ 02:00 │ Backup FULL     │ Backup FULL     │ Backup FULL       │
│ 03:00 │ CHECKDB Weekly  │                 │                   │
│       │ (1st: Full)     │                 │                   │
│ 04:00 │                 │                 │ Statistics Update │
│ 06:00 │ Backup DIFF     │ Backup DIFF     │ Backup DIFF       │
│ 18:00 │ Backup DIFF     │ Backup DIFF     │ Backup DIFF       │
│ Every │ Backup LOG      │ Backup LOG      │ Backup LOG        │
│ 30min │ (24/7)          │ (24/7)          │ (24/7)            │
└──────────────────────────────────────────────────────────────┘
```

### SQL Agent Jobs

Defined in [sql_agent_schedule_playbook.sql](sql_agent_schedule_playbook.sql)

| Job Name | Schedule | Frequency | Purpose |
|----------|----------|-----------|---------|
| **Backup FULL - Daily 2AM** | Daily | 02:00 AM | Full database backup |
| **Backup DIFF - Every 12h** | Daily | 06:00 AM & 06:00 PM | Differential backup |
| **Backup LOG - Every 30 min** | Daily | Every 30 minutes | Transaction log backup |
| **CHECKDB Weekly PHYSICAL_ONLY** | Weekly | Sunday 03:00 AM | Fast integrity check |
| **CHECKDB Monthly Full** | Monthly | 1st Sunday 03:00 AM | Deep integrity check |
| **IndexOptimize Weekly** | Weekly | Saturday 01:00 AM | Index defragmentation |
| **Statistics Update Weekly** | Weekly | Saturday 04:00 AM | Statistics maintenance |

### Job Configuration Details

Each job is configured with:

```sql
-- Job creation
EXEC msdb.dbo.sp_add_job
    @job_name = N'Job Name',
    @enabled = 1,
    @description = N'Description';

-- Job step (TSQL command)
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'Job Name',
    @step_name = N'Step 1',
    @subsystem = N'TSQL',
    @database_name = N'master',
    @command = N'EXECUTE master.dbo.StoredProcedure...';

-- Schedule definition
EXEC msdb.dbo.sp_add_schedule
    @schedule_name = N'Schedule Name',
    @freq_type = 4,              -- Daily, Weekly, Monthly
    @freq_interval = 1,          -- Day of week/month
    @active_start_time = 020000; -- HHMMSS format

-- Attach schedule to job
EXEC msdb.dbo.sp_attach_schedule
    @job_name = N'Job Name',
    @schedule_name = N'Schedule Name';

-- Register job on server
EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'Job Name';
```

## Configuration

### Backup Configuration

**Location:** [playbook.sql](playbook.sql)

```sql
-- Backup directory
@Directory = N'C:\Backup'  -- Change to your path

-- Network share example:
@Directory = N'\\BackupServer\SQLBackups\ServerName'

-- Azure Blob Storage example:
@Directory = N'https://storageaccount.blob.core.windows.net/container/'
```

**Retention Periods:**

```sql
-- Full and Differential backups
@CleanupTime = 168  -- 168 hours = 7 days

-- Transaction log backups
@CleanupTime = 72   -- 72 hours = 3 days

-- Adjust based on your requirements
```

**Backup Options:**

| Parameter | Default | Options | Purpose |
|-----------|---------|---------|---------|
| `@Verify` | Y | Y/N | Verify backup after creation |
| `@Compress` | Y | Y/N | Enable backup compression |
| `@CheckSum` | Y | Y/N | Calculate backup checksums |
| `@DatabasesInParallel` | Y | Y/N | Process multiple DBs simultaneously |
| `@LogToTable` | Y | Y/N | Log operations to CommandLog |
| `@ChangeBackupType` | Y | Y/N | Auto-convert LOG to FULL if needed |

### Integrity Check Configuration

**Location:** [playbook.sql](playbook.sql)

```sql
-- Check type
@CheckCommands = 'CHECKDB'  -- Options: CHECKDB, CHECKALLOC, CHECKCATALOG

-- Physical only (faster)
@PhysicalOnly = 'Y'  -- Y = fast check, N = full check

-- Parallel execution
@DatabasesInParallel = 'Y'  -- Process multiple databases
```

### Index Optimization Configuration

**Location:** [playbook.sql](playbook.sql)

```sql
-- Fragmentation thresholds
@FragmentationLevel1 = 5   -- Medium fragmentation threshold (%)
@FragmentationLevel2 = 30  -- High fragmentation threshold (%)

-- Actions for medium fragmentation (5-30%)
@FragmentationMedium = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE'

-- Actions for high fragmentation (>30%)
@FragmentationHigh = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE'

-- Statistics
@UpdateStatistics = 'ALL'
@OnlyModifiedStatistics = 'Y'  -- Skip unchanged statistics

-- Advanced options
@FillFactor = 90               -- Leave 10% free space in pages
@MaxDOP = 0                    -- Use all CPUs (0 = automatic)
@TimeLimit = 3600              -- Stop after 1 hour (seconds)
```

### Email Notifications

Configure SQL Server Database Mail first, then add alerts:

```sql
-- Enable Database Mail
EXEC sp_configure 'Database Mail XPs', 1;
RECONFIGURE;

-- Configure SQL Agent to send email on job failure
EXEC msdb.dbo.sp_update_job
    @job_name = N'Backup FULL - Daily 2AM',
    @notify_level_email = 2,  -- 2 = on failure
    @notify_email_operator_name = N'DBA Team';
```

## Monitoring and Logging

### CommandLog Table

All maintenance operations are logged to `master.dbo.CommandLog`:

```sql
-- View recent operations
SELECT
    ID,
    DatabaseName,
    CommandType,
    Command,
    StartTime,
    EndTime,
    DATEDIFF(SECOND, StartTime, EndTime) AS DurationSeconds,
    ErrorNumber,
    ErrorMessage
FROM master.dbo.CommandLog
ORDER BY StartTime DESC;
```

### Check Backup History

```sql
-- Recent backups by database
SELECT
    DatabaseName,
    CommandType,
    StartTime,
    EndTime,
    DATEDIFF(MINUTE, StartTime, EndTime) AS DurationMinutes
FROM master.dbo.CommandLog
WHERE CommandType LIKE 'BACKUP%'
    AND StartTime >= DATEADD(DAY, -7, GETDATE())
ORDER BY DatabaseName, StartTime DESC;
```

### Check Integrity Results

```sql
-- Recent integrity checks
SELECT
    DatabaseName,
    CommandType,
    StartTime,
    EndTime,
    ErrorMessage
FROM master.dbo.CommandLog
WHERE CommandType LIKE '%CHECK%'
    AND StartTime >= DATEADD(MONTH, -1, GETDATE())
ORDER BY StartTime DESC;
```

### Check Index Optimization

```sql
-- Recent index operations
SELECT
    DatabaseName,
    CommandType,
    StartTime,
    EndTime,
    DATEDIFF(MINUTE, StartTime, EndTime) AS DurationMinutes
FROM master.dbo.CommandLog
WHERE CommandType LIKE '%INDEX%'
    AND StartTime >= DATEADD(WEEK, -1, GETDATE())
ORDER BY StartTime DESC;
```

### SQL Agent Job History
```sql
-- Check job execution history
SELECT
    j.name AS JobName,
    h.run_date,
    h.run_time,
    CASE h.run_status
        WHEN 0 THEN 'Failed'
        WHEN 1 THEN 'Succeeded'
        WHEN 2 THEN 'Retry'
        WHEN 3 THEN 'Canceled'
        WHEN 4 THEN 'In Progress'
    END AS Status,
    h.run_duration,
    h.message
FROM msdb.dbo.sysjobs j
INNER JOIN msdb.dbo.sysjobhistory h ON j.job_id = h.job_id
WHERE j.name LIKE '%Backup%' OR j.name LIKE '%CHECKDB%' OR j.name LIKE '%Index%'
ORDER BY h.run_date DESC, h.run_time DESC;
```

## Use Cases
The [use_cases/](use_cases/) directory contains advanced examples and scenarios:

### 1. Backup Use Cases

**File:** [use_cases/backup_ola_hallengren.sql](use_cases/backup_ola_hallengren.sql)

15 example scenarios (A-P):

- **Example A:** Local backup with compression and checksums
- **Example B:** Network share backup
- **Example C:** Multi-file backup (striping for performance)
- **Example D:** Azure Blob Storage backup
- **Example E:** AWS S3 backup
- **Example F-H:** Encrypted backups (AES-256 with certificates)
- **Example I-K:** Third-party tools (LiteSpeed, SQL Backup Pro, SQL Safe)
- **Example L:** Mirrored backup (dual destinations)
- **Example M:** Data Domain Boost integration
- **Example N-P:** Custom directory structures

### 2. Integrity Check Use Cases

**File:** [use_cases/dbcc_check_ola_hallengren.sql](use_cases/dbcc_check_ola_hallengren.sql)

10 example scenarios (A-J):

- **Example A:** Full integrity check (CHECKDB + CHECKALLOC + CHECKCATALOG)
- **Example B:** Physical-only check (fast)
- **Example C:** Extended logical checks (comprehensive)
- **Example D:** Data purity check
- **Example E:** Check without indexes (tables only)
- **Example F:** Filegroup-specific check
- **Example G:** Table-specific check
- **Example H:** CHECKALLOC only (disk allocation)
- **Example I:** CHECKCATALOG only (system catalog)
- **Example J:** Custom database list

### 3. Index and Statistics Use Cases

**File:** [use_cases/index_statistics_ola_hallengren.sql](use_cases/index_statistics_ola_hallengren.sql)

Complete configuration example + 10 usage scenarios (A-J):

- **Full Configuration:** All parameters with detailed comments
- **Example A:** Index rebuild only
- **Example B:** Index reorganize only
- **Example C:** Both rebuild and reorganize
- **Example D:** Statistics update only
- **Example E:** Combined index + statistics maintenance
- **Example F:** TempDB sort operations
- **Example G:** Partition-level maintenance
- **Example H:** Time-limited operations
- **Example I:** Specific table targeting
- **Example J:** Specific index targeting

## Best Practices

### Backup Strategy

1. **Test Restores Regularly**
   - Restore backups to test environment monthly
   - Verify backup integrity and recoverability
   - Document restore procedures

2. **Monitor Backup Size Trends**
   - Track backup file sizes over time
   - Alert on unexpected growth
   - Plan storage capacity accordingly

3. **Offsite Backup Storage**
   - Copy backups to offsite location
   - Use Azure/AWS for disaster recovery
   - Implement 3-2-1 backup rule (3 copies, 2 media types, 1 offsite)

4. **Document Recovery Objectives**
   - Define RPO (Recovery Point Objective): 30 minutes with log backups
   - Define RTO (Recovery Time Objective): Based on backup size
   - Test RTO regularly

### Integrity Checks

1. **Don't Skip Integrity Checks**
   - Corruption can spread silently
   - Weekly checks minimum (daily for critical systems)
   - Monthly deep checks required

2. **Review Check Results**
   - Monitor CommandLog for errors
   - Investigate and resolve corruption immediately
   - Never ignore CHECKDB warnings

3. **Plan for VLDB**
   - Very Large Databases may need longer maintenance windows
   - Consider filegroup-level checks
   - Use table-level checks for flexibility

### Index Optimization

1. **Optimize During Low-Activity Periods**
   - Saturday nights typically low activity
   - Avoid business hours
   - Monitor blocking and wait stats

2. **Balance Fragmentation vs. Maintenance Cost**
   - 5-10% fragmentation often acceptable
   - Don't over-optimize small tables
   - Focus on frequently accessed indexes

3. **Statistics are Critical**
   - Update statistics after index maintenance
   - Use OnlyModifiedStatistics = Y for efficiency
   - Consider asynchronous statistics updates (SQL 2014+)

4. **Monitor Index Usage**
   - Remove unused indexes
   - Focus maintenance on most-used indexes
   - Review index usage quarterly

### SQL Agent Jobs

1. **Stagger Job Start Times**
   - Avoid concurrent resource-intensive jobs
   - Index maintenance before statistics
   - Full backups before differential

2. **Set Realistic Timeouts**
   - Allow sufficient time for completion
   - Use time limits to prevent overnight runs
   - Adjust based on database growth

3. **Enable Job History Logging**
   - Keep 30-90 days of history
   - Monitor for duration trends
   - Alert on job failures

4. **Document Maintenance Windows**
   - Communicate schedules to stakeholders
   - Adjust for business requirements
   - Review and update quarterly

### Security

1. **Encrypt Backups for Sensitive Data**
   - Use TDE (Transparent Data Encryption) or backup encryption
   - Protect encryption keys
   - Document key management procedures

2. **Secure Backup Locations**
   - Restrict access to backup directories
   - Use NTFS permissions
   - Audit backup access

3. **Use Service Accounts**
   - Dedicated service account for SQL Agent
   - Minimum required permissions
   - Regular password rotation