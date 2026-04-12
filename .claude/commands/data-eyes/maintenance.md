---
name: maintenance
description: SQL Server maintenance assistant — backup, integrity, index, and stats using Ola Hallengren scripts
---

# /maintenance Command

> Interactive maintenance setup using Ola Hallengren's SQL Server Maintenance Solution

## Usage

```
/maintenance <describe what you need>
```

## Examples

```
/maintenance "set up full backups daily to C:\Backup with 7-day retention"
/maintenance "create weekly index optimization for all user databases"
/maintenance "I need a schedule for all 7 SQL Agent maintenance jobs"
/maintenance "show me integrity check scenarios"
/maintenance "set up hourly log backups to Azure Blob Storage"
/maintenance "how do I configure differential backups every 12 hours?"
```

---

## What This Skill Does

1. Reads the existing maintenance scripts from `maintenance/` at invocation time — scripts are always the ground truth
2. Maps your maintenance need to the right Ola Hallengren script and scenario
3. Adapts the SQL to your environment (database list, backup path, retention, schedule)
4. Outputs the adapted script as copy-paste SQL or writes it to `maintenance/generated/`
5. Offers optional execution via `sqlcmd` after explicit confirmation

---

## Process

### Step 1: Read Maintenance Scripts

Use Glob to discover all available scripts:
```
Glob("maintenance/**/*.sql")
```

Then read the relevant scripts based on user need:
- `maintenance/playbook.sql` — core routines (backup, integrity, index, stats with Ola Hallengren parameters)
- `maintenance/sql_agent_schedule_playbook.sql` — creates the 7 pre-configured SQL Agent jobs
- `maintenance/use_cases/backup_ola_hallengren.sql` — 15 backup scenarios (local, network, Azure, AWS, encrypted)
- `maintenance/use_cases/dbcc_check_ola_hallengren.sql` — 10 integrity check scenarios (CHECKDB, CHECKALLOC, filegroups)
- `maintenance/use_cases/index_statistics_ola_hallengren.sql` — 10 index optimization scenarios (rebuild, reorganize, partitions)

### Step 2: Map to Use Case

| User says... | Scripts to read |
|---|---|
| backup, log backup, full, differential, Azure, S3, network share | `playbook.sql` + `use_cases/backup_ola_hallengren.sql` |
| integrity, CHECKDB, corruption, consistency | `playbook.sql` + `use_cases/dbcc_check_ola_hallengren.sql` |
| index, fragmentation, rebuild, reorganize, defragment | `playbook.sql` + `use_cases/index_statistics_ola_hallengren.sql` |
| statistics, stats, update, stale | `playbook.sql` + `use_cases/index_statistics_ola_hallengren.sql` |
| schedule, SQL Agent, jobs, all jobs, automate | `sql_agent_schedule_playbook.sql` |
| show all / general overview | all scripts |

### Step 3: Adapt Parameters

After reading the scripts, identify and adapt these key Ola Hallengren parameters:

| Parameter | What to ask / infer |
|---|---|
| `@Databases` | Ask: "Which databases? Options: USER_DATABASES / ALL_DATABASES / specific DB name" |
| `@Directory` | Ask: "Local path (e.g. C:\Backup) or leave empty if using @URL" |
| `@URL` | Ask: "Azure Blob URL or S3 path? (only for cloud backups)" |
| `@BackupType` | Infer from description: FULL / DIFF / LOG |
| `@CleanupTime` | Ask: "Retention in hours? Default: 168 (7 days)" |
| `@Compress` | Default Y — confirm if user wants uncompressed |
| `@Verify` | Default Y — always verify backup integrity |
| `@Checksum` | Default Y — recommended for production |
| `@DatabasesInParallel` | Default Y for multiple databases |
| `@LogToTable` | Default Y — enables monitoring via CommandLog |

Present the adapted script with all parameters clearly labeled. Explain what each parameter does.

### Step 4: Output

1. Show the adapted SQL as a copy-paste block with a brief explanation of what it does
2. Write the adapted script to `maintenance/generated/<descriptive-name>.sql`
   - If the file already exists, ask: "Overwrite `maintenance/generated/<name>.sql`? (yes/no)"
3. Ask: "Ready to execute via sqlcmd? (yes/no)"
4. If yes: check `$MSSQL_CONNECTION` environment variable
   - If set: use it — format: `sqlcmd -S <server> -U <user> -P <pass> -i maintenance/generated/<name>.sql`
   - If not set: prompt — "Please provide: Server name, Username, Password"
5. Show the exact command before running it. Only execute after user sees and accepts it.

---

## Output Rules

**Read-only queries (SELECT-based diagnostics):**
- Explain what the script does and what the results mean
- Present the SQL as a copy-paste block
- Offer: "Want me to run this via sqlcmd? (yes/no)"

**Maintenance scripts (CREATE JOB, EXECUTE DatabaseBackup, etc.):**
- Explain exactly what objects will be created or what operations will run
- Show the adapted SQL
- Write to `maintenance/generated/<descriptive-name>.sql`
- Ask: "Ready to execute? (yes/no)"
- ONLY run after explicit "yes"

**SQL Agent job scripts:**
- List the 7 jobs that will be created with their schedules
- Warn: "This will create SQL Agent jobs on your server"
- Write to `maintenance/generated/sql_agent_jobs.sql`
- Ask: "Ready to create these jobs? (yes/no)"
- ONLY run after explicit "yes"

---

## Important Safety Rules

- NEVER execute scripts that create SQL Agent jobs without explicit user confirmation
- NEVER run scripts against ALL_DATABASES without confirming the scope with the user
- The `@Databases` parameter controls blast radius — always confirm before production runs
- If the user seems uncertain, default to showing the script and recommending a test run on a non-production database first
- Always print the generated file path so the user can inspect it independently
