# Automating SQL Server Maintenance with Ola Hallengren's Scripts

Every SQL Server that has no maintenance plan is an accident waiting to happen. Corruption grows silently. Indexes fragment. Backups go untested. And then one day, the restore fails — and nobody knows why.

This article walks through a production-ready maintenance automation solution built on top of **Ola Hallengren's SQL Server Maintenance Solution** — the most widely trusted maintenance framework in the SQL Server community. The goal is to give you a complete, repeatable setup: backups, integrity checks, and index optimization, all running automatically through SQL Server Agent.

---

## Why Ola Hallengren?

Ola Hallengren's scripts ([ola.hallengren.com](https://ola.hallengren.com)) are three stored procedures that wrap the entire surface area of SQL Server maintenance:

- `DatabaseBackup` — backups with built-in verification, compression, checksums, and cloud support
- `DatabaseIntegrityCheck` — CHECKDB and related integrity commands with smart filtering
- `IndexOptimize` — fragmentation-based rebuild/reorganize with statistics updates

They are free, open-source, production-proven, and trusted by enterprises worldwide. Using them as the foundation means you are not reinventing the wheel — you are standing on thousands of production hours of testing.

---

## What the Solution Includes

```
maintenance/
├── playbook.sql                         # Core maintenance routines
├── sql_agent_schedule_playbook.sql      # Creates 7 SQL Agent jobs
└── use_cases/
    ├── backup_ola_hallengren.sql        # 15 backup scenarios
    ├── dbcc_check_ola_hallengren.sql    # 10 integrity check scenarios
    └── index_statistics_ola_hallengren.sql  # 10 index scenarios
```

The `playbook.sql` is the core — it contains the actual maintenance calls. The `sql_agent_schedule_playbook.sql` wraps those calls into SQL Agent jobs with schedules. The `use_cases/` directory is a reference library of advanced scenarios.

---

## Prerequisites

Before running anything, you need Ola Hallengren's scripts installed in your `master` database. Download and execute `MaintenanceSolution.sql` from [ola.hallengren.com](https://ola.hallengren.com). Verify the stored procedures exist:

```sql
SELECT name FROM master.sys.procedures
WHERE name IN ('DatabaseBackup', 'DatabaseIntegrityCheck', 'IndexOptimize');
```

You also need a backup directory. On a local instance:

```bash
mkdir C:\Backup
```

For cloud backups (Azure, AWS), you will configure `@URL` instead of `@Directory` — covered in the use cases section below.

---

## Part 1: Backup Strategy

A solid backup strategy covers three layers: full, differential, and transaction log. Each serves a different purpose in your recovery model.

### Full Backup — Daily at 2 AM

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases              = 'USER_DATABASES',
    @Directory              = N'C:\Backup',
    @BackupType             = 'FULL',
    @Verify                 = 'Y',
    @Compress               = 'Y',
    @Checksum               = 'Y',
    @CleanupTime            = 168,        -- 7-day retention
    @LogToTable             = 'Y',
    @DatabasesInParallel    = 'Y';
```

Key parameters to understand:

- `@Verify = 'Y'` — Runs a RESTORE VERIFYONLY after each backup. This catches corrupt backup files before you need them.
- `@Compress = 'Y'` — Typically reduces backup size by 50–60%.
- `@Checksum = 'Y'` — Detects corruption in the backup file itself.
- `@CleanupTime = 168` — Automatically deletes backup files older than 168 hours (7 days). Without this, your disk fills up.
- `@DatabasesInParallel = 'Y'` — Backs up multiple databases simultaneously, reducing the backup window.

### Differential Backup — Every 12 Hours

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases   = 'USER_DATABASES',
    @Directory   = N'C:\Backup',
    @BackupType  = 'DIFF',
    @Verify      = 'Y',
    @Compress    = 'Y',
    @Checksum    = 'Y',
    @CleanupTime = 168;
```

Differentials capture all changes since the last full backup. They are faster than a full backup and reduce your recovery time — instead of replaying hours of transaction logs, you restore the full, apply the differential, then replay only the logs since the differential.

### Transaction Log Backup — Every 30 Minutes

```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases        = 'USER_DATABASES',
    @Directory        = N'C:\Backup',
    @BackupType       = 'LOG',
    @Verify           = 'Y',
    @Compress         = 'Y',
    @Checksum         = 'Y',
    @CleanupTime      = 72,             -- 3-day retention for logs
    @ChangeBackupType = 'Y';            -- Falls back to FULL if no full exists
```

Log backups are what give you point-in-time recovery. With a 30-minute log backup schedule, your Recovery Point Objective (RPO) is 30 minutes — meaning at most 30 minutes of data can be lost in a disaster. `@ChangeBackupType = 'Y'` is a safety net: if no full backup exists yet, it automatically runs a full instead of failing.

---

## Part 2: Integrity Checks

Corruption in SQL Server databases is rare, but when it happens, it is catastrophic — and it can go undetected for weeks. Integrity checks are your early warning system.

### Weekly Fast Check — Sunday at 3 AM

```sql
EXECUTE master.dbo.DatabaseIntegrityCheck
    @Databases           = 'USER_DATABASES',
    @CheckCommands       = 'CHECKDB',
    @PhysicalOnly        = 'Y',
    @LogToTable          = 'Y',
    @DatabasesInParallel = 'Y';
```

`@PhysicalOnly = 'Y'` makes CHECKDB check only the physical structure of pages — it skips logical consistency checks. This runs 30–40% faster and catches the most common corruption: storage-level bit rot. Run this every week.

### Monthly Deep Check — First Sunday at 3 AM

```sql
EXECUTE master.dbo.DatabaseIntegrityCheck
    @Databases           = 'USER_DATABASES',
    @CheckCommands       = 'CHECKDB',
    @LogToTable          = 'Y',
    @DatabasesInParallel = 'Y';
```

The full CHECKDB — no `@PhysicalOnly`. This validates logical consistency, all indexes, all catalogs. It is resource-intensive but thorough. Once a month is a sensible frequency for most production databases.

---

## Part 3: Index Optimization

Index fragmentation is a silent performance killer. Over time, as rows are inserted, updated, and deleted, index pages become out-of-order and contain gaps. This increases I/O for reads and slows down queries.

### Weekly Index Maintenance — Saturday at 1 AM

```sql
EXECUTE master.dbo.IndexOptimize
    @Databases              = 'USER_DATABASES',
    @FragmentationLow       = NULL,
    @FragmentationMedium    = 'INDEX_REORGANIZE,INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationHigh      = 'INDEX_REBUILD_ONLINE,INDEX_REBUILD_OFFLINE',
    @FragmentationLevel1    = 5,
    @FragmentationLevel2    = 30,
    @UpdateStatistics       = 'ALL',
    @OnlyModifiedStatistics = 'Y',
    @LogToTable             = 'Y';
```

The fragmentation strategy:

| Fragmentation | Action |
|---|---|
| < 5% | No action — the overhead of maintenance outweighs the benefit |
| 5–30% | REORGANIZE — online, low-lock operation, sufficient for medium fragmentation |
| > 30% | REBUILD — rebuilds the index from scratch, eliminates fragmentation completely |

`INDEX_REBUILD_ONLINE` is attempted first when fragmentation is high — it allows reads and writes to continue during the rebuild. If online rebuild is not available (Standard Edition or heap tables), it falls back to `INDEX_REBUILD_OFFLINE`.

`@OnlyModifiedStatistics = 'Y'` is critical: it skips statistics that have not changed since the last update. This makes the statistics update step efficient even on large databases.

---

## Part 4: SQL Agent Jobs

Everything above is meaningless without a scheduler. The `sql_agent_schedule_playbook.sql` creates 7 pre-configured SQL Agent jobs that wire up the playbook routines to a schedule.

| Job | Schedule | Purpose |
|---|---|---|
| Backup FULL - Daily 2AM | Daily 02:00 | Full database backup |
| Backup DIFF - Every 12h | 06:00 and 18:00 | Differential backup |
| Backup LOG - Every 30 min | Every 30 minutes, 24/7 | Transaction log backup |
| CHECKDB Weekly PHYSICAL_ONLY | Sunday 03:00 | Fast integrity check |
| CHECKDB Monthly Full | 1st Sunday 03:00 | Deep integrity check |
| IndexOptimize Weekly | Saturday 01:00 | Index defragmentation |
| Statistics Update Weekly | Saturday 04:00 | Statistics refresh |

The jobs are created using standard `msdb` system stored procedures:

```sql
EXEC msdb.dbo.sp_add_job        @job_name = N'Backup FULL - Daily 2AM', @enabled = 1;
EXEC msdb.dbo.sp_add_jobstep    @job_name = N'Backup FULL - Daily 2AM', @command = N'EXECUTE master.dbo.DatabaseBackup ...';
EXEC msdb.dbo.sp_add_schedule   @schedule_name = N'Daily 2AM', @freq_type = 4, @active_start_time = 020000;
EXEC msdb.dbo.sp_attach_schedule @job_name = N'Backup FULL - Daily 2AM', @schedule_name = N'Daily 2AM';
EXEC msdb.dbo.sp_add_jobserver  @job_name = N'Backup FULL - Daily 2AM';
```

---

## Part 5: Advanced Scenarios

The `use_cases/` folder is a reference library of 35+ scenarios covering the most common variations. A few highlights:

**Azure Blob Storage backup:**
```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases   = 'USER_DATABASES',
    @URL         = N'https://storageaccount.blob.core.windows.net/sqlbackups',
    @BackupType  = 'FULL',
    @Credential  = N'MyAzureCredential',
    @Compress    = 'Y';
```

**AES-256 encrypted backup:**
```sql
EXECUTE master.dbo.DatabaseBackup
    @Databases          = 'USER_DATABASES',
    @Directory          = N'C:\Backup',
    @BackupType         = 'FULL',
    @Encrypt            = 'Y',
    @EncryptionAlgorithm = 'AES_256',
    @ServerCertificate  = N'MyBackupCertificate';
```

**Filegroup-specific integrity check:**
```sql
EXECUTE master.dbo.DatabaseIntegrityCheck
    @Databases     = 'MyDatabase',
    @CheckCommands = 'CHECKFILEGROUP',
    @FileGroups    = 'PRIMARY';
```

---

## Monitoring the Results

All maintenance operations are logged to `master.dbo.CommandLog`. This is your audit trail and diagnostic tool:

```sql
-- Review the last 7 days of maintenance activity
SELECT
    DatabaseName,
    CommandType,
    StartTime,
    EndTime,
    DATEDIFF(SECOND, StartTime, EndTime) AS DurationSeconds,
    ErrorMessage
FROM master.dbo.CommandLog
WHERE StartTime >= DATEADD(DAY, -7, GETDATE())
ORDER BY StartTime DESC;
```

A null `ErrorMessage` means success. Any error here needs investigation immediately — especially from integrity checks.

---

## Best Practices Before You Deploy

**Test your restores.** A backup you have never restored is a backup you do not have. Run a test restore to a separate server monthly.

**Do not skip integrity checks.** Corruption spreads. Catching it early is the difference between a restore exercise and a data loss event.

**Stagger your jobs.** Do not run IndexOptimize and a full backup at the same time. The job schedule in this solution is already designed to avoid overlap — keep it that way.

**Adjust retention for your environment.** `@CleanupTime = 168` (7 days) is a starting point. Align it with your actual RPO and RTO requirements.

---

## Meet Your Agentic Maintenance Assistant

Deploying the maintenance solution is a one-time task. The ongoing work is different: a new server that needs the same 7 jobs configured, a backup path that needs to change because you are moving to Azure, a stakeholder who needs to know whether last Saturday's index job ran. Small tasks, but each one requires opening the right script, understanding the right parameters, and adapting them without breaking anything.

That is what the `/maintenance` skill is for.

---

### A Real Scenario

Your team just provisioned a new SQL Server for a production workload. You need to set up all 7 maintenance jobs — but this server backs up to Azure Blob Storage, not a local path, and you want 14-day retention instead of the default 7.

```
/maintenance "set up full, differential, and log backups to Azure, with 14-day retention"
```

The skill reads `playbook.sql`, `sql_agent_schedule_playbook.sql`, and `use_cases/backup_ola_hallengren.sql`. It responds:

> I will adapt the Azure Blob Storage backup scenario. A few things I need from you:
>
> 1. **Azure Blob URL** — the container URL for your backups (format: `https://<account>.blob.core.windows.net/<container>/`)
> 2. **Azure Credential name** — the SQL Server credential you have created for Blob Storage access
> 3. **Which databases?** — USER_DATABASES, ALL_DATABASES, or a specific list?
>
> Using your answers, here is the adapted backup routine:
>
> ```sql
> -- FULL BACKUP (Daily @ 2AM) — Azure Blob Storage, 14-day retention
> EXECUTE master.dbo.DatabaseBackup
>     @Databases           = 'USER_DATABASES',
>     @URL                 = N'https://mystorageacct.blob.core.windows.net/sqlbackups/',
>     @Credential          = N'AzureBackupCredential',
>     @BackupType          = 'FULL',
>     @Verify              = 'Y',
>     @Compress            = 'Y',
>     @Checksum            = 'Y',
>     @CleanupTime         = 336,   -- 14 days (336 hours)
>     @LogToTable          = 'Y',
>     @DatabasesInParallel = 'Y';
> ```
>
> I have also prepared the DIFF and LOG variants with matching retention. Written to `maintenance/generated/azure_backup_14day.sql`.
>
> Do you also want me to create the SQL Agent job schedule? I can run `sql_agent_schedule_playbook.sql` adapted for these three backup types. (yes/no)

You review the file, confirm the parameters, type `yes`. The skill asks one more time before executing — because job creation is irreversible and touches the server's Agent configuration.

> About to execute: `sqlcmd -S yourserver -U sa -i maintenance/generated/sql_agent_azure_jobs.sql`
>
> This will create 3 SQL Agent jobs (FULL, DIFF, LOG) on the server. Ready? (yes/no)

You type `yes`. The jobs are created. The skill confirms by listing the job names and their schedules.

---

### Invocation Examples

```
/maintenance "set up hourly log backups to Azure Blob Storage"
/maintenance "configure AES-256 encrypted backups with a server certificate"
/maintenance "weekly index optimization for a single database, not all user databases"
/maintenance "create all 7 SQL Agent maintenance jobs for a new server"
/maintenance "show me the integrity check scenarios — I need a filegroup-specific CHECKDB"
/maintenance "what is the right fragmentation threshold for reorganize vs. rebuild?"
/maintenance "how do I set up a mirrored backup to two destinations?"
/maintenance "check what maintenance ran last night and whether any errors occurred"
```

---

### How It Works Under the Hood

When you invoke `/maintenance`, Claude immediately runs:

```
Glob("maintenance/**/*.sql")
```

It discovers all 5 scripts across the `playbook.sql`, `sql_agent_schedule_playbook.sql`, and the 3 use case files. It then routes your request:

| Your words | Scripts read |
|---|---|
| backup, full, differential, log, Azure, S3, encrypted | `playbook.sql` + `use_cases/backup_ola_hallengren.sql` |
| integrity, CHECKDB, corruption, filegroup | `playbook.sql` + `use_cases/dbcc_check_ola_hallengren.sql` |
| index, fragmentation, rebuild, reorganize, statistics | `playbook.sql` + `use_cases/index_statistics_ola_hallengren.sql` |
| schedule, jobs, SQL Agent, automate, all jobs | `sql_agent_schedule_playbook.sql` |

The adapted script is always written to `maintenance/generated/` before any execution is offered — so you have a file you can inspect, version, and re-run independently of the skill.

**The confirmation gate is non-negotiable.** The skill will never execute a script that creates SQL Agent jobs or runs a backup command without an explicit "yes" from you. It will show you exactly what command it intends to run before running it.

---

### What This Changes

Before the skill: you open the `use_cases/` folder, find the closest scenario, copy it, open `playbook.sql` to cross-reference the parameter defaults, adapt the values, paste into SSMS, double-check, run.

After the skill: you describe what you need. The skill finds the right scenario across all 5 scripts, asks for the environment-specific values it needs, fills in the rest with sensible defaults it explains, writes a permanent adapted file, and offers to execute — all while keeping you in control of every step that touches the server.

The scripts do not change. What changes is the work between "I need to set up backups on a new server" and "the jobs are created and confirmed."

---

*Data Eyes is an open-source SQL Server toolkit. The maintenance solution covered in this article lives in the [maintenance/](https://github.com/lorenzouriel/data-eyes/tree/main/maintenance) folder of the repository.*
