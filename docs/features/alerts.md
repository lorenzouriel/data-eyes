# Alerts

Data Eyes checks every configured SQL Server for the conditions in the alert
catalog below and sends changes through the rules and channels on the
[Notifications](notifications.md) page. Everyone signed in can open **Alerts**
in the top navigation to see what is open and what happened recently;
administrators can turn each alert on or off and tune it, fleet-wide or per
instance.

Source: [`backend/app/modules/alerts/`](../../backend/app/modules/alerts) and
[`frontend/src/features/alerts/`](../../frontend/src/features/alerts).

## How alerts are evaluated

- **When:** at the end of every collector cycle (`COLLECTOR_INTERVAL_SECONDS`,
  default 60s), each enabled alert runs if its frequency is due: every cycle,
  every 5 minutes, hourly, or daily. After a backend restart, every enabled
  alert runs once at the next cycle and then follows its frequency.
- **Connection first:** each instance is probed before its checks run. An
  unreachable instance raises only **SQL Server Connection**; its other
  checks pause and run as soon as it is back, instead of all reporting UNKNOWN.
- **Load:** checks run one at a time per instance and at most two instances at
  once, on the collector's background SQL lane. A check that finds the lane
  busy is retried next cycle rather than reported as a failure.
- **Thresholds:** SQL returns raw measurements and Data Eyes applies the
  thresholds, so a changed threshold applies at the next run. "Above" alerts
  fire at or above the threshold (log 90% full); "below" alerts fire at or
  below it (5 GB free). Some conditions have a fixed severity instead of a
  threshold (a SUSPECT database is always critical).
- **What a message contains:** the alert name, the transition or event, the
  worst value, and up to five offending subjects (drive, database, job, login,
  file). Query text is never included, because messages leave the system.

### State alerts and event alerts

**State alerts** hold a severity that later clears, such as a log that is 92%
full. They are written to `alert_state` and, as the category `alert.<key>`, to
`metric_snapshot`. That gives every alert a trend history and makes it visible
to MCP agents through `get_latest_snapshot` and `get_severity_trend`. A
notification is sent when the severity changes; as before, the first sample
only establishes a baseline.

**Event alerts** are one-off occurrences that never clear: a deadlock, a failed
job, a restart, a burst of failed logins. Each occurrence is stored once in
`alert_event` (deduplicated, so re-reading the same error log line is harmless)
and delivered once. Several occurrences of the same alert on one instance in a
cycle are combined into one message. When an event alert is first enabled, it
records a starting point and does not replay history.

## Controlling alerts

On **Alerts → Settings**, choose a scope: **All instances** for the
fleet-wide setting, or one instance to override it. Blank fields inherit, and
the inherited value is shown as the placeholder: catalog default, then the
fleet-wide setting, then the instance override.

| Setting | Effect |
|---|---|
| On | Turns the alert on or off immediately. Turning an alert off clears its current state, so turning it back on starts from a new baseline instead of sending a stale recovery. |
| Frequency | How often the check runs: every cycle (~1 min), every 5 min, hourly, or daily. |
| Warning / Critical | Thresholds in the unit shown. Warning must come before critical: lower for "above" alerts, higher for "below" alerts. |
| Double check | A severity change only counts after it is observed this many times in a row (default 1, or 2 for noisy gauges such as memory and I/O). Replaces the separate "Double Check Alert". |
| Excluded databases | Comma-separated databases the alert ignores, for alerts that report per database. Fleet-wide and instance exclusions add together. |
| Reset | Deletes the saved setting for this scope so it inherits again. |

Two items that were alerts on the original list are now settings on
notification rules, because they decide who is told and when, not what is
detected:

- **Re-notify** (was "Alert Without Clear"): while a state alert stays open,
  repeat it every N minutes.
- **Escalate:** stay silent on the change and notify only once the alert has
  been open N minutes, for example to a manager's channel. An escalation rule
  sends a recovery only for incidents it escalated, and ignores event alerts.

## Alert catalog

"Every" is the default frequency. "Needs" is the SQL Server permission the
check uses in addition to `CONNECT SQL`; see [Permissions](#permissions).
Defaults are recorded in
[`thresholds.yaml`](../../.claude/knowledge-base/_static/thresholds.yaml); a
backend test fails if the two drift apart.

#### Availability

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| SQL Server Connection | `sql_server_connection` | state | 1 min | fixed | on, double check ×2 | CONNECT SQL |
| SQL Server Restarted | `sql_server_restarted` | event | 1 min | fixed | on | VIEW SERVER STATE |
| SQL Agent Stopped | `agent_service_stopped` | state | 5 min | fixed | on | VIEW SERVER STATE |
| Database Status | `database_status` | state | 1 min | fixed | on | public |
| AlwaysOn AG Health | `ag_health` | state | 1 min | ≥ 51,200 / 512,000 KB | on | VIEW SERVER STATE |
| AG Failover | `ag_failover` | event | 1 min | fixed | on | VIEW SERVER STATE |
| AG Data Loss Risk | `ag_data_loss_risk` | state | 1 min | ≥ 60 / 300 seconds | on | VIEW SERVER STATE |
| Failover Cluster Status | `failover_cluster_status` | state | 5 min | fixed | on | VIEW SERVER STATE |
| Log Shipping Latency | `log_shipping_latency` | state | 5 min | ≥ 60 / 240 minutes | on | SELECT on msdb tables |

#### Backup & integrity

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| DB Without Full Backup | `full_backup_age` | state | 1 h | ≥ 24 / 48 hours | on | SELECT on msdb tables |
| DB Without Log Backup | `log_backup_age` | state | 5 min | ≥ 60 / 240 minutes | on | SELECT on msdb tables |
| Backup Failed | `backup_failed` | event | 5 min | fixed | on | securityadmin (xp_readerrorlog) — high privilege |
| CheckDB Databases | `checkdb_age` | state | 24 h | ≥ 7 / 14 days | on | public |
| Database Corruption | `database_corruption` | state | 1 h | fixed | on | SELECT on master.dbo.CommandLog (Ola Hallengren) |
| Page Corruption | `page_corruption` | state | 5 min | ≥ — / 1 pages | on | SELECT on msdb tables |
| I/O Errors 823/824/825 | `io_corruption_errors` | event | 5 min | fixed | on | securityadmin (xp_readerrorlog) — high privilege |

#### Storage

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| Disk Space | `disk_space` | state | 5 min | ≤ 20 / 5 GB | on | VIEW SERVER STATE |
| Transaction Log Health | `transaction_log_health` | state | 1 min | ≥ 75 / 90 % | on | VIEW SERVER STATE |
| MaxSize Growth | `maxsize_growth` | state | 5 min | ≥ 80 / 90 % | on | public |
| Database Growth | `database_growth` | state | 24 h | ≥ 10 / 25 %/day | on | public |
| Slow File Growth | `slow_file_growth` | event | 5 min | ≥ 1,000 / 10,000 ms | on | ALTER TRACE (default trace) |
| Too Many VLFs | `vlf_count` | state | 24 h | ≥ 1,000 / 5,000 VLFs | on | VIEW SERVER STATE |
| IO Pending | `io_pending` | state | 1 min | ≥ 5,000 / 15,000 ms | on, double check ×2 | VIEW SERVER STATE |
| Slow Disk | `slow_disk` | state | 5 min | ≥ 20 / 50 ms | on, double check ×2 | VIEW SERVER STATE |

#### Tempdb

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| Tempdb MDF Utilization | `tempdb_data_utilization` | state | 1 min | ≥ 85 / 95 % | on, double check ×2 | VIEW SERVER STATE |
| Tempdb Version Store | `tempdb_version_store` | state | 5 min | ≥ 30 / 50 % | on | VIEW SERVER STATE |
| Tempdb Log Usage | `tempdb_log_usage` | state | 1 min | ≥ 70 / 90 % | on | VIEW SERVER STATE |
| Tempdb Allocation Contention | `tempdb_contention` | state | 1 min | ≥ 5 / 20 tasks | on, double check ×2 | VIEW SERVER STATE |

#### Performance

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| CPU Utilization | `cpu_utilization` | state | 1 min | ≥ 80 / 95 % | on | VIEW SERVER STATE |
| Memory Available | `memory_available` | state | 1 min | ≤ 2,048 / 512 MB | on, double check ×2 | VIEW SERVER STATE |
| Page Life Expectancy | `page_life_expectancy` | state | 1 min | ≤ 300 / 100 seconds | on, double check ×2 | VIEW SERVER STATE |
| Memory Grants Pending | `memory_grants_pending` | state | 1 min | ≥ 1 / 5 queries | on, double check ×2 | VIEW SERVER STATE |
| Worker Thread Exhaustion | `threadpool_exhaustion` | state | 1 min | ≥ 80 / 95 % | on, double check ×2 | VIEW SERVER STATE |
| Blocked Process | `blocking` | state | 1 min | ≥ 30 / 120 seconds | on | VIEW SERVER STATE |
| Long Running Process | `long_running_process` | state | 1 min | ≥ 600 / 3,600 seconds | on | VIEW SERVER STATE |
| Slow Queries | `slow_queries` | state | 5 min | ≥ 5,000 / 30,000 ms | on | VIEW SERVER STATE |
| DeadLock | `deadlock` | event | 1 min | fixed | on | VIEW SERVER STATE |
| Query Plan Regression | `query_regression` | state | 1 h | ≥ 1 / 10 queries | on | VIEW DATABASE STATE |
| Database Errors | `database_errors` | event | 5 min | fixed | on | securityadmin (xp_readerrorlog) — high privilege |
| Login Failed | `login_failed` | event | 5 min | ≥ 5 / 50 logins | on | securityadmin (xp_readerrorlog) — high privilege |

#### Maintenance

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| Job Failed | `job_failed` | event | 5 min | fixed | on | SELECT on msdb tables |
| Job Disabled or Deleted | `job_disabled_or_deleted` | event | 5 min | fixed | on | SELECT on msdb tables |
| Rebuild Failed | `rebuild_failed` | event | 5 min | fixed | on | SELECT on master.dbo.CommandLog (Ola Hallengren) |
| Index Fragmentation | `index_fragmentation` | state | 24 h | ≥ 30 / 60 % | off | VIEW SERVER STATE |
| Stale Statistics | `stale_statistics` | state | 24 h | ≥ 30 / 60 days | on | VIEW ANY DEFINITION |
| Identity Values / Int-Bigint Limit | `identity_values` | state | 24 h | ≥ 80 / 90 % | on | VIEW ANY DEFINITION |
| New Database Not Covered | `new_database` | event | 5 min | fixed | on | SELECT on msdb tables |
| Server Needs Hotfix | `version_support` | state | 24 h | ≤ 365 / 0 days | on | public |

#### Configuration & security

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| Server Configuration Changed | `config_changed` | event | 5 min | fixed | on | public |
| Max Server Memory Not Set | `max_server_memory_unset` | state | 24 h | fixed | on | VIEW SERVER STATE |
| Auto-Shrink or Auto-Close On | `auto_shrink_close` | state | 24 h | fixed | on | public |
| Page Verify Not CHECKSUM | `page_verify` | state | 24 h | fixed | on | public |
| Sysadmin Membership Changed | `sysadmin_changed` | event | 5 min | fixed | on | VIEW ANY DEFINITION |
| New Login Created | `login_created` | event | 5 min | fixed | on | VIEW ANY DEFINITION |
| sa Login Enabled | `sa_enabled` | state | 24 h | fixed | on | VIEW ANY DEFINITION |
| Certificate Expiry | `certificate_expiry` | state | 24 h | ≤ 30 / 7 days | on | VIEW ANY DEFINITION |

#### Data Eyes

| Alert | Key | Kind | Every | Warning / Critical | Default | Needs |
|---|---|---|---|---|---|---|
| Notification Channel Failing | `notification_delivery_failing` | state | 5 min | ≥ 1 / 3 failures | on | none (repository) |

### Changes from the original alert list

| Original | Now |
|---|---|
| DB Without Backup | Removed; covered by DB Without Full Backup and DB Without Log Backup. |
| Blocked Process, Blocked Long Process | Merged into **Blocked Process** (warning 30s, critical 120s). |
| Log Full, Large LDF File | Merged into **Transaction Log Health**: log used %, the reason the log cannot be reused, and a warning when the log is larger than the data. |
| Identity Values, Int-Bigint Limit | Merged into **Identity Values / Int-Bigint Limit**. |
| New Ignored DB, Database Created | Merged into **New Database Not Covered**, which says whether the database has a full backup yet. DB Without Full Backup measures a new database from its creation time, so it gets a grace period. |
| Double Check Alert | The per-alert **Double check** setting. |
| Alert Without Clear | The rule's **Re-notify** and **Escalate** settings. |
| Daily DB CheckList | The [Daily DB checklist](#daily-db-checklist) report. |
| Traces Size | Removed (SQL Trace is deprecated). |
| Server Needs Hotfix | Checks Microsoft's fixed extended-support end dates instead of a cumulative-update list that would go stale. Warns a year ahead; critical once unsupported. |
| Update Statistics | Renamed **Stale Statistics**. |
| Index Fragmentation | Kept, off by default: it scans every index and is rarely urgent. |
| (new) | SQL Agent Stopped, AG Failover, AG Data Loss Risk, Log Shipping Latency, Backup Failed, I/O Errors 823/824/825, Too Many VLFs, Tempdb Version Store, Tempdb Log Usage, Tempdb Allocation Contention, Page Life Expectancy, Memory Grants Pending, Worker Thread Exhaustion, Query Plan Regression, Server Configuration Changed, Max Server Memory Not Set, Auto-Shrink or Auto-Close On, Page Verify Not CHECKSUM, Sysadmin Membership Changed, New Login Created, sa Login Enabled, Certificate Expiry, Notification Channel Failing. |

## Permissions

Most checks need only `VIEW SERVER STATE`, which the monitoring login already
has. The rest are optional. An alert whose permission is missing shows
**Missing permission** on **Alerts → Overview** under "Checks that could not run" (a state alert also goes UNKNOWN), and
you can turn it off. Review
[`mcp/sql/provision-alerting-permissions.sql`](../../mcp/sql/provision-alerting-permissions.sql)
before granting anything; it is a template, not a script to run unchanged.

- **msdb tables:** backup age, page corruption, jobs, log shipping, new databases.
- **`VIEW ANY DEFINITION`:** sysadmin and login changes, sa, certificates, and
  statistics and identity columns in every database.
- **`ALTER TRACE`:** Slow File Growth reads the default trace.
- **Ola Hallengren `CommandLog`:** Database Corruption and Rebuild Failed.
  Without the table, these checks report nothing rather than failing.
- **Error log (`securityadmin`):** Backup Failed, I/O Errors 823/824/825,
  Database Errors and Login Failed read the SQL Server error log with
  `xp_readerrorlog`, which SQL Server only allows for `securityadmin` members.
  `securityadmin` can grant itself further permissions, so treat it as close to
  sysadmin: grant it only to a dedicated, tightly held login, or leave those
  four alerts off.

## Daily DB checklist

Replaces the "Daily DB CheckList" alert. Once a day, at or after the chosen UTC
hour, Data Eyes sends one summary to the selected channels. For each instance
it lists the open alerts, event counts from the last 24 hours, and checks that
could not run. It goes straight to the channels and ignores rules, quiet hours
and cooldowns. Configure it on **Alerts → Daily checklist** (administrators only).

## Monitoring Data Eyes itself

- **Notification Channel Failing** reports a channel with failed deliveries in
  the last hour, delivered through your other channels.
- Alerts run inside the collector loop, so a stopped collector cannot alert
  about itself. Point an external uptime monitor at
  `GET /api/health/collector`. It returns `503` with `"status": "stale"` when
  no cycle has completed for five intervals (at least five minutes). It is
  separate from `/api/health`, so a slow SQL Server never restarts the
  container.

## Limits

- Replication latency is not covered; Log Shipping Latency is.
- TLS certificates are not visible to T-SQL. Certificate Expiry covers
  certificates in `master` (TDE, backup encryption).
- Slow File Growth reads only the current default trace file, so growth events
  in a file that rolled over between checks are missed.
- The error log alerts read only the current log file, so lines written just
  before `sp_cycle_errorlog` can be missed.
- Sysadmin Membership Changed records its baseline from what the login can
  see. Granting `VIEW ANY DEFINITION` later reports existing members as added,
  once.
- Query Plan Regression needs SQL Server 2017+ with Query Store on; Too Many
  VLFs needs 2016 SP2+. On older versions they report "Not supported on this
  server".
- Index Fragmentation and the per-database checks can exceed the 30-second
  query limit on very large servers; they then report "Timed out".
- Existing notification rules whose category was a dashboard health category
  (`backup_health`, `errors`, `overall`, …) no longer match anything. Edit them
  and pick an alert.

## Checks

From `backend`, run `uv run pytest -p no:cacheprovider`. The alert tests use
canned DMV rows and never contact SQL Server. Repository tests run against a
disposable PostgreSQL database when `NOTIFICATION_TEST_POSTGRES_DSN` is set (see
[Notifications](notifications.md#checks)).
