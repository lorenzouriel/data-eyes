# The SQL Scripts Collection: A DBA's Personal Toolkit

Every DBA accumulates a personal library of SQL scripts. The queries you reach for when something breaks at 2 AM. The permission templates you have written a dozen times across different environments. The quick diagnostics that tell you in thirty seconds whether the server is healthy.

The `sql-scripts/` folder in Data Eyes is exactly that — a curated, organized collection of 80+ SQL Server scripts covering 18 operational topics. Not a framework, not a product. Just the scripts that get used in the real world, organized so you can find them when you need them.

This article walks through the collection: what it contains, how it is organized, and when to reach for each category.

---

## How the Collection Is Organized

```
sql-scripts/
├── audit/
├── backup_recovery/
├── custom_alert_emails/
├── database_size/
├── free_space/
├── functions/
├── helps/
│   └── spatial_data/
├── index/
├── lock/
├── query_store/
├── server/
├── sql_access/
├── sql_agent/
├── sql_docker/
├── sql_profiler/
├── ssis/
├── ssrs/
└── triggers/
```

Each sub-folder is a topic. Within each folder, scripts are named for what they do. The naming convention is the documentation.

---

## The Categories

### `lock/` — Blocking and Locking

The three scripts every DBA runs when someone reports that "the database is slow":

**`blocking_sessions_report.sql`** — The first script to run during a blocking incident. Queries `sys.dm_exec_requests` to show every session that is currently waiting, what it is waiting for, and which session is blocking it.

```sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.wait_type,
    r.wait_time / 1000.0 AS wait_time_seconds,
    r.wait_resource,
    t.text AS query_text
FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.blocking_session_id > 0;
```

**`sp_who2.sql`** — The classic. Shows all active sessions with their status, blocking chain, and the database they are using. Fast to read at a glance.

**`specific_session.sql`** — When you know the session ID, this gives you the full picture: current query, wait type, locks held, transaction state. Use it after `blocking_sessions_report.sql` identifies the blocker.

---

### `index/` — Index Management

Nine scripts covering the full lifecycle of SQL Server indexes.

**`check_index_fragmentation.sql`** — Before rebuilding anything, measure first. This script uses `sys.dm_db_index_physical_stats` to show the fragmentation percentage of every index in the database:

```sql
SELECT
    OBJECT_NAME(i.object_id) AS TableName,
    i.name AS IndexName,
    ips.index_type_desc,
    ips.avg_fragmentation_in_percent,
    ips.page_count
FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
WHERE ips.avg_fragmentation_in_percent > 5
ORDER BY ips.avg_fragmentation_in_percent DESC;
```

**`rebuild_index.sql`** / **`reorganize_index.sql`** — The two remediation actions. Rebuild completely recreates the index (eliminates fragmentation, updates statistics). Reorganize defragments online at the leaf level (faster, less I/O, but less thorough). The fragmentation threshold: < 30% → reorganize, > 30% → rebuild.

**`clustered_index.sql`**, **`nonclustered_index.sql`**, **`nonclustered_index_include.sql`** — Templates for creating each index type. The `_include` version covers the common pattern of adding non-key columns to an index to avoid key lookups without bloating the key.

**`clustered_columnstore_index.sql`** / **`nonclustered_columnstore_index.sql`** — Columnstore templates for analytical workloads and data warehouse tables where scan-heavy queries need maximum compression and batch mode execution.

**`statistics.sql`** — Creates statistics on specific columns manually, for situations where the auto-created statistics are not sufficient.

**`ola_hallengren.sql`** — A reference script that invokes `IndexOptimize` from the maintenance solution, useful when you want ad-hoc index maintenance on a specific table or database without running the scheduled SQL Agent job.

---

### `backup_recovery/` — Backup and Restore

The scripts that matter most when something goes wrong.

**`backup_history.sql`** — Queries `msdb.dbo.backupset` to show recent backup history by database, type, and duration. The script you run to confirm last night's backup completed before you make a production change.

```sql
SELECT
    bs.database_name,
    bs.type AS backup_type,
    bs.backup_start_date,
    bs.backup_finish_date,
    DATEDIFF(MINUTE, bs.backup_start_date, bs.backup_finish_date) AS duration_minutes,
    bmf.physical_device_name
FROM msdb.dbo.backupset bs
INNER JOIN msdb.dbo.backupmediafamily bmf ON bs.media_set_id = bmf.media_set_id
WHERE bs.backup_start_date >= DATEADD(DAY, -7, GETDATE())
ORDER BY bs.backup_start_date DESC;
```

**`restore_script.sql`** — A template for a full + differential + log restore sequence. The script that saves time when every minute counts during a recovery.

**`restore_start_time.sql`** — Estimates how long a restore will take based on the backup file size and historical restore rates. Useful when you need to give a realistic ETA to stakeholders during an incident.

**`search_backups_folder.sql`** — Queries the backup directory for available backup files when you need to find the right backup for a point-in-time restore.

**`clean_backup_history.sql`** — The `msdb.dbo.backupset` table grows indefinitely. This script prunes old backup history records to keep `msdb` healthy.

**`change_simple_to_full.sql`** / **`check.sql`** — Changing a database to FULL recovery model is a prerequisite for transaction log backups. These scripts handle the change and verify the current recovery model across all databases.

---

### `database_size/` — Storage Monitoring

Six scripts for understanding where your disk space is going.

**`database_files_detail.sql`** — Shows every data and log file for every database: physical location, current size, used space, free space, and autogrowth setting. The first script to run when disk space is running low.

**`largest_table.sql`** — Identifies the top tables by row count and allocated space. When a database grows unexpectedly, this is how you find out which table is responsible.

**`database_storage_breakdown.sql`** — Breaks down storage by database across the instance. Essential for capacity planning.

**`database_storage_alert.sql`** — A threshold-based query that returns databases where data or log files have less than a configurable percentage of free space. Schedule this as a SQL Agent job to generate alerts before disks fill up.

**`memory_settings.sql`** — Shows the current `max server memory` configuration and how much memory SQL Server is actually using. Useful during memory pressure investigation.

**`total_used_storage.sql`** — A quick instance-wide summary: total storage allocated vs. total space used across all databases.

---

### `free_space/` — Disk and Filegroup Management

**`partition_filegroup_allocation.sql`** — For databases that use multiple filegroups (typically for partitioned tables or archive data), this shows space allocation per filegroup and which tables live in each.

**`database_cleanup.sql`** — Removes old data from specific tables (truncate or batched delete). A parameterized template for archive and cleanup operations.

**`shrink.sql`** — Shrinks data or log files. Use with caution — shrinking a data file causes severe index fragmentation and should only be done in specific circumstances (after removing a large amount of data permanently, for example). The script includes warnings about when not to use it.

---

### `sql_access/` — User and Permission Management

The scripts you reach for whenever someone needs access to a database or an access audit is required.

**`role_and_login.sql`** — Creates a SQL Server login and database user, assigns them to a database role. The template for provisioning a new user.

**`grant_view_access.sql`** / **`grant_statements_access.sql`** — Granular permission grants. `grant_view_access.sql` gives SELECT on all tables in a schema. `grant_statements_access.sql` grants specific statement-level permissions (INSERT, UPDATE, DELETE) on targeted objects.

**`deny_view_access.sql`** — Explicit DENY overrides any GRANT. Used to prevent access to specific tables for a user who has broad role membership.

**`users_info.sql`** — Lists all users in the current database with their roles and permissions. The starting point for access audits.

**`who_is_trying_access.sql`** — Queries SQL Server audit or login failure logs to identify failed connection attempts. Useful when investigating unauthorized access attempts.

**`drop_user.sql`** — Cleanly removes a user and their associated database permissions before removing the login.

---

### `sql_agent/` — Job Monitoring and Management

**`monitor_currently_agent_jobs.sql`** — Shows all currently running SQL Agent jobs with their start time, duration, and step. The script you open when a maintenance job is taking longer than expected.

**`check_running_and_stop_jobs.sql`** — Identifies running jobs and provides the `sp_stop_job` call to stop a specific job if it is hanging or consuming resources it should not.

**`sql_agent_sessions.sql`** — Shows which sessions are SQL Agent job sessions vs. user connections. Useful for distinguishing maintenance activity from user workload.

**`purge_job_history.sql`** — The `msdb.dbo.sysjobhistory` table grows indefinitely. This script deletes old job history records, keeping the table manageable and `msdb` performance healthy.

**`grant_access.sql`** — Grants specific permissions for a user to view or manage SQL Agent jobs without being a sysadmin.

---

### `query_store/` — Query Store Analysis

Ten scripts for working with SQL Server's built-in query history tracking (SQL Server 2016+).

**`enable.sql`** — The Query Store configuration script. Enable it on any database where you want historical query analysis.

**`last_queries_executed.sql`** — Shows the most recently executed queries with their execution plans and runtime statistics.

**`longest_avg_exec_time.sql`** — Top queries by average execution time. The starting point for identifying slow queries.

**`highest_avg_row_count.sql`** — Top queries by average rows returned. Queries returning millions of rows when they should return hundreds are often missing predicates or indexes.

**`queries_that_recently_regressed_performance.sql`** — Compares the last execution interval to the previous one and surfaces queries whose performance degraded. This is the script that catches plan regressions automatically.

**`historical_regression_performance.sql`** — Shows the performance history of a specific query over time, with plan changes highlighted. When you know which query regressed, this shows you exactly when it happened.

**`force_plan.sql`** — Forces a specific execution plan for a query. When a plan regression is confirmed and you need an immediate fix while the root cause is investigated, plan forcing stops the bleeding.

**`queries_w_multiple_plans.sql`** — Identifies queries that have been compiled with multiple execution plans. Multiple plans for the same query often indicate parameter sniffing issues.

---

### `audit/` — Activity Auditing

**`audit_toolkit.sql`** — Sets up SQL Server Audit to track specific events (logins, data access, permission changes) and write them to a file or SQL Server table. A starting point for compliance-driven audit requirements.

**`audit_users_table.sql`** — Creates a trigger-based audit on a specific table, logging all inserts, updates, and deletes with the user, timestamp, and changed values. For tables where you need a full change history without enabling server-level audit.

---

### `custom_alert_emails/` — Database Mail and Custom Alerts

**`enable_database_mail.sql`** — Configures SQL Server Database Mail from scratch: creates a mail profile, configures the SMTP server, and tests the setup.

**`dbo.usp_send_job_custom_email.sql`** — A stored procedure that generates and sends a formatted HTML email with job execution results. More useful than the default SQL Agent notification emails — includes execution time, duration, error messages, and a link to the job history.

---

### `sql_profiler/` — Trace and Profiling

**`automatically_profiler.sql`** — Creates a server-side trace (the programmatic equivalent of SQL Profiler) that captures slow queries above a configurable duration threshold. Writes to a trace file for offline analysis.

**`check_traces.sql`** — Shows currently active traces on the instance. Useful for confirming a trace is running or finding traces left open by previous sessions.

---

### `ssrs/` — SQL Server Reporting Services

Six scripts for managing SSRS environments without needing the Report Manager UI.

**`list_ssrs_objects.sql`** — Lists all reports, data sources, and folders in the SSRS catalog. The fastest way to get an inventory of what is deployed.

**`info_reports.sql`** — Shows report metadata: creation date, last modification, who created it, and the report definition XML.

**`subscriptions.sql`** — Lists all report subscriptions with their schedule, delivery method, and parameters. Essential for auditing scheduled report delivery.

**`users_access_ssrs.sql`** / **`check_ssrs_permissions.sql`** — Show who has access to the SSRS instance and at what permission level. The starting point for SSRS access audits.

**`analyze.sql`** — Queries the SSRS execution log to show report execution frequency, duration, and failure rate.

---

### `ssis/` — SQL Server Integration Services

**`create_jobs_schedule.sql`** — Creates a SQL Agent job that executes an SSIS package from the SSIS catalog. The template for scheduling SSIS package execution through the Agent.

**`create_proc_trigger_job.sql`** — Creates a stored procedure that triggers a SQL Agent job. The pattern for situations where you need to invoke an SSIS package from T-SQL (e.g., at the end of another process).

**`ssis_maintenance.sql`** — Cleans up old SSIS catalog execution records. The SSISDB execution log grows indefinitely — this script prunes it to keep performance healthy.

---

### `server/` — Server Configuration and Administration

**`server_info.sql`** — A quick instance snapshot: SQL Server version, edition, CPU count, memory, collation, and key configuration settings. The first script to run when connecting to an unfamiliar server.

**`linked_server.sql`** — Creates a linked server connection to another SQL Server instance. Includes security configuration for the mapped credentials.

**`query_with_other_server.sql`** — Examples of four-part name queries and `OPENQUERY` against linked servers. The template for distributed queries.

**`server_roles.sql`** — Lists all server-level role memberships. The starting point for privilege audits at the server level.

---

### `helps/` — Helper Scripts and Templates

A collection of useful utilities that do not fit neatly into one category.

**`iterate_clean_tables.sql`** — A cursor-based pattern for iterating over a list of tables and executing a cleanup operation on each. The template for batch maintenance operations.

**`check_cascade.sql`** — Shows the cascade delete/update relationships on a table. Before dropping or modifying a table, this reveals what dependent tables will be affected.

**`create_credential_proxy.sql`** — Creates a SQL Agent credential and proxy for executing SSIS or PowerShell steps under a specific Windows account.

**`maintenance_solution.sql`** — A reference script showing how to download and install Ola Hallengren's scripts directly from the web (using `xp_cmdshell` or SQLCLR, depending on your setup).

**`median_of_total_points.sql`** — A T-SQL implementation of a median calculation (which SQL Server does not have a native aggregate for). Useful for analytical queries where AVG is too sensitive to outliers.

**`spatial_data/`** — Three scripts demonstrating SQL Server's spatial data capabilities: creating polygon geometries, querying spatial relationships, and working with route/path data.

---

### `triggers/` and `functions/`

**`trg_prevent_delete_where.sql`** — An `INSTEAD OF DELETE` trigger template that prevents deletion of rows matching a condition. Useful for protecting reference data or audit records from accidental deletion.

**`dbo.google_data.sql`** — A scalar function that formats coordinates for Google Maps integration. An example of extending SQL Server with business-specific utility functions.

---

### `sql_docker/`

A Docker Compose configuration for spinning up a SQL Server instance locally for development and testing. Includes a `.gitignore` pattern for excluding the data volumes from version control.

---

## When to Reach for Which Category

| Situation | Category |
|---|---|
| "Something is slow" | `lock/` first, then `query_store/` |
| "Disk is filling up" | `database_size/`, `free_space/` |
| "Who has access to X?" | `sql_access/`, `audit/` |
| "Last night's backup?" | `backup_recovery/` |
| "Job failed" | `sql_agent/` |
| "Index fragmentation?" | `index/` |
| "Query slowed down recently?" | `query_store/` |
| "Who is trying to connect?" | `sql_access/` |
| "SSRS report not working?" | `ssrs/` |
| "Configure email alerts?" | `custom_alert_emails/` |

---

## Meet Your Agentic SQL Scripts Assistant

Eighty scripts across 18 sub-folders is a useful library. But a library is only as good as your ability to find the right book under pressure. When blocking sessions are piling up or a disk alert fires at 11 PM, the last thing you want is to navigate folder by folder trying to remember which script does what and whether you need to change the database name or the session ID.

The `/sql-scripts` skill is your direct interface to the collection. It routes your natural-language description to the right sub-folder, reads the matching scripts, adapts the parameters, and delivers ready-to-run SQL.

---

### A Real Scenario

Monday morning. A developer pings you: "the application is hanging — can you check if something is blocking?"

```
/sql-scripts "there are blocking sessions on the server"
```

The skill maps "blocking sessions" to the `lock/` sub-folder. It reads `blocking_sessions_report.sql`, `sp_who2.sql`, and `specific_session.sql`. It responds:

> **Two scripts for blocking investigation:**
>
> **1. `blocking_sessions_report.sql`** — Start here. Shows every session currently waiting, what it is waiting for, and which session is blocking it.
>
> ```sql
> SELECT
>     r.session_id,
>     r.blocking_session_id,
>     r.wait_type,
>     r.wait_time / 1000.0 AS wait_time_seconds,
>     r.wait_resource,
>     t.text AS query_text
> FROM sys.dm_exec_requests r
> CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
> WHERE r.blocking_session_id > 0;
> ```
>
> **What to look for:**
> - `blocking_session_id` → the session causing the chain. Use that ID in the next script.
> - `wait_resource` → identifies the locked object (e.g., `5:1:72` = database 5, file 1, page 72).
> - Long `wait_time_seconds` → how long this session has been stuck.
>
> **2. `specific_session.sql`** — Once you have the blocking session ID, use this to see exactly what query it is running and what locks it holds.
>
> Want me to run `blocking_sessions_report.sql` against your server? (yes/no)

You type `yes`. The skill executes the query and returns the results. Session 52 is blocking sessions 87, 91, and 103. It continues:

> **Session 52 is the head blocker.** Running for 14 minutes. Here is the query holding the lock:
>
> *(shows the query text from `specific_session.sql` result)*
>
> This is a long-running `UPDATE` without an explicit transaction commit. Options:
> - Wait for it to complete (check estimated remaining time via sys.dm_exec_requests)
> - Kill the session if it is safe to do so: `KILL 52;`
>
> Want me to generate the KILL command for your review? (yes/no)

If you say yes, the skill writes `sql-scripts/generated/lock/kill_session_52.sql`, shows it to you, and asks for explicit confirmation before executing — because killing a session rolls back its transaction and that is irreversible.

---

### Invocation Examples

```
/sql-scripts "there are blocking sessions on the server"
/sql-scripts "grant read access to a new user named john on the Sales database"
/sql-scripts "check index fragmentation on the Orders table in the Warehouse database"
/sql-scripts "my SQL Agent job failed last night, show me the history and error"
/sql-scripts "who has sysadmin rights on this instance?"
/sql-scripts "configure database mail with Gmail SMTP"
/sql-scripts "which queries regressed performance in the last hour — use Query Store"
/sql-scripts "how much free space is left in each database file?"
/sql-scripts "I need to restore a database to a specific point in time"
/sql-scripts "set up an audit on the Customers table to track all changes"
```

---

### How It Works Under the Hood

The skill uses a keyword routing table with 18 entries — one per sub-folder — to scope the file reads before loading anything:

```
"blocking, lock, deadlock"     → Glob("sql-scripts/lock/*.sql")
"index, fragmentation"         → Glob("sql-scripts/index/*.sql")
"backup, restore, recovery"    → Glob("sql-scripts/backup_recovery/**/*.sql")
"user, permission, grant"      → Glob("sql-scripts/sql_access/*.sql")
"agent, job, schedule"         → Glob("sql-scripts/sql_agent/*.sql")
"query store, plan regression" → Glob("sql-scripts/query_store/*.sql")
... 12 more entries
```

This is the key design decision: the skill never reads all 80+ scripts at once. Your "blocking sessions" invocation loads 3 scripts. Your "index fragmentation" invocation loads 9. The result is a focused, relevant answer — not an overwhelming dump of every script that mentions indexes.

After routing and reading, the skill selects the 1–3 most relevant scripts, adapts parameters to what you have told it, and outputs based on what the script does:

| Script type | Output |
|---|---|
| SELECT-only (DMVs, sys.* views, msdb) | Copy-paste SQL + optional `sqlcmd` run |
| CREATE / ALTER objects | Write to `sql-scripts/generated/<sub-folder>/<name>.sql` → confirm before run |
| Destructive (DROP, KILL, DENY, SHRINK) | Explain impact → write to generated/ → explicit "yes" required |

**Fallback:** If your description does not match any routing entry, the skill reads `helps/` for general utilities and asks a clarifying question with four options — monitoring, access/permissions, performance/indexes, backup/restore.

---

### What This Changes

The collection has scripts for nearly every common DBA task. The problem before the skill was not that the scripts were missing — it was the overhead between "I have a problem" and "I have the right script adapted for my environment, ready to run."

That overhead is: remembering which sub-folder, finding the right file, reading the parameter comments, adapting the values, copying to SSMS, running, and interpreting the output.

The `/sql-scripts` skill removes every step in that chain except the last one — you still read the results and make the decision. What you no longer do is spend ten minutes navigating a file tree while an incident is in progress.

The scripts are the same. The library is the same. What changes is how fast you get from the problem description to the right script, adapted and ready.

---

*Data Eyes is an open-source SQL Server toolkit. The SQL Scripts collection covered in this article lives in the [sql-scripts/](https://github.com/lorenzouriel/data-eyes/tree/main/sql-scripts) folder of the repository.*
