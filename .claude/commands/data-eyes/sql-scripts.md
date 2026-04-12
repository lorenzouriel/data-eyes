---
name: sql-scripts
description: Find, adapt, and run SQL Server scripts from the sql-scripts library — covers 18 DBA topics with smart sub-folder routing
---

# /sql-scripts Command

> Find the right SQL Server script for any DBA task across 18 topic areas

## Usage

```
/sql-scripts <describe your problem or need>
```

## Examples

```
/sql-scripts "there are blocking sessions on the server"
/sql-scripts "grant read access to a new user named john"
/sql-scripts "check index fragmentation on the Orders database"
/sql-scripts "my SQL Agent job failed last night, show me the history"
/sql-scripts "how much space is left in the database files?"
/sql-scripts "who is trying to access my SQL Server?"
/sql-scripts "enable query store on a database"
/sql-scripts "I need to restore a database to a point in time"
/sql-scripts "create a custom email alert for a failed job"
/sql-scripts "check SSRS report subscriptions"
```

---

## What This Skill Does

1. Maps your problem to the right sub-folder using a keyword routing table
2. Reads only the relevant scripts — no scanning all 80+ files
3. Selects the 1-3 best matching scripts for your specific need
4. Adapts parameters to your environment (DB names, user names, thresholds)
5. Outputs read-only scripts as copy-paste SQL, and write/destructive scripts with a confirmation gate

---

## Sub-folder Routing Map

Before reading any scripts, route the user's problem to the correct sub-folder:

| Keywords | Sub-folder |
|---|---|
| blocking, lock, deadlock, wait, sessions, sp_who, who is connected | `lock/` |
| index, fragmentation, rebuild, reorganize, columnstore, nonclustered, clustered, statistics on index | `index/` |
| backup, restore, recovery, point-in-time, backup history, clean backup, search backup | `backup_recovery/` |
| size, storage, largest table, sp_spaceused, database files, memory settings, total used | `database_size/` |
| shrink, free space, partition, filegroup, database cleanup | `free_space/` |
| user, permission, access, login, role, grant, deny, drop user, who has access, view access | `sql_access/` |
| agent, job, schedule, job history, running job, stop job, purge history, SQL Agent session | `sql_agent/` |
| query store, plan, plan regression, force plan, execution count, wait duration, last queries | `query_store/` |
| audit, audit table, audit toolkit, who changed, auditing | `audit/` |
| trace, profiler, SQL Profiler, automatically profiler, check traces | `sql_profiler/` |
| SSRS, report, subscription, report permissions, list reports, analyze reports | `ssrs/` |
| SSIS, package, SSIS job, SSIS maintenance, create job schedule, proc trigger job | `ssis/` |
| trigger, prevent delete, trg | `triggers/` |
| linked server, server info, server roles, server role, query other server, query with other | `server/` |
| email, alert, database mail, custom email, SMTP, send email, mail profile | `custom_alert_emails/` |
| spatial, polygon, route, geometry | `helps/spatial_data/` |
| docker, container, SQL docker | `sql_docker/` |
| credential, proxy, maintenance solution, iterate tables, median, cascade, change language | `helps/` |

**If no keyword matches:** read `helps/` for general utilities, then ask:
"Is your question about: (a) monitoring/sessions, (b) access/permissions, (c) performance/indexes, (d) backup/restore, (e) something else?"

---

## Process

### Step 1: Route

Parse the user's message. Find the best matching keywords in the routing table above.
For each matched sub-folder:
```
Glob("sql-scripts/<matched-sub-folder>/*.sql")
```

If the match is ambiguous (e.g., "index" could mean index fragmentation OR index statistics), route to both sub-folders and read all scripts.

### Step 2: Read and Select

Read all `.sql` files in the matched sub-folder(s).
Review each script's content and comments to understand its purpose.
Select the **1-3 most relevant scripts** based on the user's specific need.

If the user's need is very general (e.g., "show me everything about locks"), present all scripts in the sub-folder with a brief description of each.

### Step 3: Adapt

After selecting the script(s), identify parameters to customize:

| Parameter type | How to handle |
|---|---|
| Database name | Ask if not stated; use `[DatabaseName]` as placeholder if multiple |
| Login / user name | Ask if not stated (e.g., for grant/deny scripts) |
| Table name or object | Ask if not stated; use `[SchemaName].[TableName]` as placeholder |
| Date range | Use sensible defaults (last 7 days), explain the default |
| Row count / TOP N | Default to TOP 10 or TOP 25, explain |
| Session ID | Ask the user to provide from a prior query result |

Show the adapted SQL with placeholders clearly marked with `-- TODO: replace` comments.

### Step 4: Output

**Read-only scripts (SELECT, sys.* queries, DMV queries):**
- Present the adapted SQL as a copy-paste block
- Explain what each important column in the result means
- Ask: "Want me to run this via sqlcmd? (yes/no)"
- If yes: check `$MSSQL_CONNECTION`, prompt if absent, run and interpret output

**Scripts that CREATE or ALTER objects (indexes, stored procedures, jobs, credentials):**
- Explain exactly what will be created or changed
- Show the adapted SQL
- Write to `sql-scripts/generated/<sub-folder>/<descriptive-name>.sql`
  - If file already exists: ask "Overwrite? (yes/no)"
- Ask: "Ready to execute? (yes/no)"
- ONLY run after explicit "yes"

**Scripts with EXEC (stored procedures, system procs):**
- Explain what the stored procedure does and its side effects
- Confirm whether it's read-only (e.g., sp_who2) or write (e.g., sp_spaceused with truncation)
- For read-only EXEC: treat as read-only script
- For write EXEC: treat as CREATE/ALTER — write to generated/, confirm before run

**Destructive operations (DROP USER, DENY, KILL session, SHRINK, DELETE):**
- Always explain the impact before showing the script
- State clearly: "This operation is irreversible" or "This will terminate active sessions"
- Write to `sql-scripts/generated/<sub-folder>/<name>.sql`
- Ask for explicit confirmation with a clear warning
- ONLY run after explicit "yes"

---

## Script Library Reference

| Sub-folder | Scripts available |
|---|---|
| `lock/` | blocking_sessions_report, sp_who2, specific_session |
| `index/` | check_index_fragmentation, clustered_index, nonclustered_index, nonclustered_index_include, clustered_columnstore_index, nonclustered_columnstore_index, rebuild_index, reorganize_index, statistics, ola_hallengren |
| `backup_recovery/` | backup_history, clean_backup_history, olla_hallengren_backup, search_backups_folder, restore_script, restore_start_time, change_simple_to_full, check (recovery model) |
| `database_size/` | database_files_detail, database_storage_alert, database_storage_breakdown, largest_table, memory_settings, sp_spaceused, total_used_storage |
| `free_space/` | database_cleanup, partition_filegroup_allocation, shrink |
| `sql_access/` | deny_view_access, drop_user, grant_statements_access, grant_view_access, role_and_login, users_info, who_is_trying_access |
| `sql_agent/` | check_running_and_stop_jobs, grant_access, monitor_currently_agent_jobs, purge_job_history, sql_agent_sessions |
| `query_store/` | enable, execution_count, force_plan, highest_avg_row_count, highest_wait_durations, historical_regression_performance, last_queries_executed, longest_avg_exec_time, queries_that_recently_regressed_performance, queries_w_multiple_plans |
| `audit/` | audit_toolkit, audit_users_table |
| `sql_profiler/` | automatically_profiler, check_traces |
| `ssrs/` | analyze, check_ssrs_permissions, info_reports, list_ssrs_objects, subscriptions, users_access_ssrs |
| `ssis/` | create_jobs_schedule, create_proc_trigger_job, ssis_maintenance |
| `triggers/` | trg_prevent_delete_where |
| `server/` | linked_server, query_with_other_server, server_info, server_roles |
| `custom_alert_emails/` | dbo.usp_send_job_custom_email, enable_database_mail |
| `helps/spatial_data/` | polygons_pt1, polygons_pt2, route |
| `sql_docker/` | docker-compose.yml, gitignore |
| `helps/` | change_language, check_cascade, comments, create_credential_proxy, iterate_clean_tables, maintenance_solution, median_of_total_points |

---

## Important Rules

- NEVER execute DROP, KILL, DENY, or SHRINK operations without explicit user confirmation
- Always explain the impact of destructive operations before presenting the script
- For `KILL <session_id>`: warn the user that this will abruptly terminate a connection and may cause transaction rollback
- For `SHRINK`: warn this is generally not recommended in production — it causes index fragmentation
- For DROP USER: confirm the user is not actively connected before suggesting the script
- If the user provides a specific script name, read and present it directly without routing
- New sub-folders added to `sql-scripts/` can be accessed by adding their keywords to the routing table in this skill file
