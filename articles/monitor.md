# Real-Time SQL Server Monitoring with Grafana

You cannot fix what you cannot see.

Most SQL Server problems — slow queries, memory pressure, failed jobs, growing databases — do not announce themselves with an error message. They degrade gradually, quietly, until someone notices that something feels slow or a disk alarm fires at 2 AM.

The solution is visibility: a monitoring stack that watches your SQL Server continuously, surfaces problems before they become incidents, and gives you historical data to understand trends.

This article walks through a complete, containerized SQL Server monitoring solution built with **Grafana** — deployable in minutes, providing 45+ metrics out of the box, and configurable for email alerting.

---

## The Architecture

```
┌─────────────────────────────────────────────────────┐
│              Monitoring Solution                     │
└─────────────────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
          ┌───▼────┐           ┌────▼─────┐
          │ Grafana│◄──────────┤  MSSQL   │
          │ :3000  │           │ Database │
          └────────┘           └──────────┘
              │
              ▼
          Email Alerts
          (SMTP/Gmail)
```

**Grafana** is the visualization layer. It connects directly to SQL Server as a data source and executes T-SQL queries to populate dashboard panels. It also handles alerting.

**Docker Compose** orchestrates the container, manages volumes for data persistence, and wires together the configuration from environment variables.

There is no custom exporter to install, no agent on the SQL Server host, no middleware. Grafana queries SQL Server directly.

---

## What's Inside the Stack

```
monitor/
├── docker-compose.yml
├── .env                              # Credentials (not committed to git)
├── grafana/
│   ├── grafana.ini                   # Grafana instance configuration
│   ├── datasources.yml               # SQL Server connection
│   ├── alerts-and-notifiers.yml      # Email alert routing
│   ├── dashboard-provider.yml        # Dashboard auto-provisioning
│   └── dashboards/
│       ├── sqlserver.json            # Comprehensive dashboard (45+ panels)
│       └── sql_server_simplified.json # Simplified dashboard (30+ panels)
└── docs/
    ├── general.md
    ├── server_performance.md
    ├── query_perfomance.md
    ├── database_space_usage.md
    ├── jobs_monitoring.md
    ├── buffer_index_management.md
    └── other_metrics.md
```

Every configuration file is provisioned automatically — no clicking through the Grafana UI to set up data sources or import dashboards. When the containers start, everything is wired up.

---

## Deploying the Stack

### Step 1: Configure your environment

Create a `.env` file in the `monitor/` directory. This file holds all credentials and is excluded from git:

```bash
# Grafana Admin
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=your_secure_password

# SQL Server connection
DB_HOST=your_server.com,1433
DB_PORT=1433
DB_NAME=master
DB_USER=monitoring_user
DB_PASSWORD=your_db_password

# Email alerts (Gmail example)
GRAFANA_SMTP_HOST=smtp.gmail.com:587
GRAFANA_SMTP_USER=alerts@yourdomain.com
GRAFANA_SMTP_PASSWORD=your_app_password
GRAFANA_SMTP_FROM_ADDRESS=alerts@yourdomain.com
GRAFANA_SMTP_FROM_NAME=SQL Monitor
GRAFANA_NOTIFICATION_ADDRESSES=dba-team@yourdomain.com

DS_MSSQL=SQLServer
```

For Gmail, you need to generate an App Password (not your regular account password). Go to your Google Account → Security → 2-Step Verification → App Passwords, generate one for "Mail", and use that value for `GRAFANA_SMTP_PASSWORD`.

For SQL Server, create a dedicated monitoring user with minimum permissions:

```sql
CREATE LOGIN [monitoring_user] WITH PASSWORD = 'YourPassword';
CREATE USER [monitoring_user] FOR LOGIN [monitoring_user];
GRANT VIEW SERVER STATE TO [monitoring_user];
GRANT VIEW DATABASE STATE TO [monitoring_user];
```

### Step 2: Start the stack

```bash
cd monitor/
docker-compose up -d
```

Docker Compose pulls the Grafana image, creates a persistent volume, and starts the container. Grafana reads the `grafana/` directory for its provisioned configuration — datasources, dashboards, and alert channels are all loaded automatically.

### Step 3: Verify

Open `http://localhost:3000` and log in with your admin credentials.

1. Navigate to **Configuration → Data Sources** — SQLServer should show a green checkmark
2. Go to **Dashboards** and open the SQL Server dashboard
3. Confirm panels are displaying data

If datasources show red, check your `.env` values and verify SQL Server is reachable from the Docker network.

---

## What the Dashboards Monitor

### Server Health

The first section gives you the overview: how long has the server been up, how many active sessions are connected, and how many idle connections are sitting open.

Active sessions doing nothing still hold connections and may hold locks. A server with 300 idle sessions and 5 active ones has a connection pooling problem worth investigating.

### Query Performance

This section is where you spend most of your time during performance investigations.

**Top 10 Slowest Queries:** Ranked by average execution time, drawn from `sys.dm_exec_query_stats` and `sys.dm_exec_sql_text`. The panel shows actual query text alongside execution count and average duration — so you can distinguish a query that is slow every run from one that only occasionally misbehaves. A query with a high execution count and a moderate duration often has more total impact than a single slow outlier.

**Query Cache Hit Rate:** The percentage of cached query plans that are actually being reused. For OLTP workloads this should stay above 98%. A low hit rate means SQL Server is recompiling plans on every execution, wasting CPU and adding latency. The usual cause is ad-hoc queries with literal values instead of parameters — each distinct value generates a separate plan, inflating the cache and reducing reuse. The fix is parameterization, or enabling *Optimize for Ad Hoc Workloads*.

**Query Latency:** Average execution time across queries currently tracked in the plan cache. Use this as a before/after signal when deploying indexes or query changes. A small percentage drop in average latency across the workload is often more meaningful than optimizing a single query in isolation.

**Query Plan Cache Efficiency:** Plan count and compilation rate together tell you whether the plan cache is growing unbounded. Rising plan count alongside a low hit rate is the signature of plan cache pollution — memory filling up with one-off plans that are never reused. Left unchecked, this can flush useful plans out of the cache and cause recompilation cascades under load.

### Server Performance

Overall server state during peak activity — what is running, what is waiting, and what is being blocked.

**Active Transactions:** Count of open transactions in the system. Long-running transactions hold locks and prevent log truncation — a single uncommitted transaction can block dozens of other queries and cause the transaction log to grow without bound. Any transaction open for more than a few minutes in an OLTP system deserves investigation.

**Overall Wait Times:** Cumulative wait time by wait type, excluding background and idle waits. This is your fastest path to identifying systemic bottlenecks: `PAGEIOLATCH_*` points to disk pressure, `LCK_M_*` points to locking contention, `SOS_SCHEDULER_YIELD` points to CPU saturation. The pattern of wait types tells you more about the root cause than any individual slow query.

**Table Locks:** Active lock requests across sessions, showing lock mode and grant status. Locks in `WAIT` state are being blocked by another session holding an incompatible lock. A cluster of waiting locks on the same object is a blocking chain — find the head blocker and you find the root cause.

**Running Threads:** The number of requests currently executing. During normal operation this tracks your active connection count. Sustained high thread counts relative to logical CPU cores indicate CPU pressure or poorly parallelized queries generating excessive parallelism.

**Open File Limits (Pending I/O):** Pending disk I/O operations waiting to complete. A high count reflects slow storage, I/O saturation, or large sequential scans. This metric spikes during backup operations and bulk loads — a spike during normal OLTP activity is a warning sign worth tracing to the responsible queries.

**Temp Tables Created on Disk:** Session space usage split between user objects and internal objects. A rising internal object page count means queries are spilling sorts or hash joins to tempdb — SQL Server needed more memory than it was granted. The usual causes are stale statistics, parameter sniffing, or `max server memory` set too low for the workload.

### Buffer and Index Management

The buffer pool is the most important memory structure in SQL Server — it holds database pages in RAM to avoid disk I/O. Three panels here matter most:

**Buffer Pool Hit Rate:** The percentage of page requests served from memory rather than disk. Below 95% is a warning sign; below 90% is a problem.

**Page Life Expectancy (PLE):** How long a page survives in the buffer pool. Sustained values below 300 seconds indicate memory pressure. For servers with 64 GB or more of RAM, expect PLE in the thousands during normal operation — a sudden drop warrants investigation.

**Memory Grants Pending:** Queries waiting for memory to execute sort or hash operations. Any sustained value above 0 means queries are queuing behind each other for memory — a sign that `max server memory` may be too low or queries are over-requesting memory.

### Database Space Usage

This section watches for the problems that sneak up on you over days and weeks:

- Database file sizes and growth trends
- Transaction log space usage (a log that fills up stops the database)
- Data file free space per database
- Row counts per table

The transaction log panel deserves attention. A log that is growing unusually fast indicates long-running transactions or high write volume. A log that is near capacity is an emergency — when it fills, no transactions can commit.

### SQL Agent Jobs

Every maintenance job in your environment is tracked here:

- **Currently running jobs** — what is executing right now
- **Job execution history** — success/failure with duration
- **Failed jobs** — with error messages
- **Scheduled vs. running** overview

This panel is what you check first when the maintenance window was last night and you want to confirm everything ran. A quick visual scan shows green (success) or red (failure) for each job.

### Wait Statistics

The wait statistics panel surfaces the top wait types in real time — the same data that `wait_statistics.sql` queries, but displayed as a live chart with historical trending. High `CXPACKET` waits, rising `PAGEIOLATCH_*`, or sudden `LCK_M_*` spikes all become visible on this panel before they cause noticeable problems.

### Backup Status

Shows the last backup time for each database by type (FULL, DIFFERENTIAL, LOG). A database that has not been backed up in over 24 hours is a risk that this panel makes immediately visible.

---

## Configuring Email Alerts

Alerts are defined in `grafana/alerts-and-notifiers.yml`. The contact point is already configured to use the SMTP settings from your `.env` file.

To create a new alert rule, go to **Alerting → Alert rules → New alert rule** in the Grafana sidebar. The form has six sections.

### Step 1 — Name

Give the rule a name that describes what it detects, not what it does. `PLE drops below 300 for 5 minutes` is useful. `Alert rule 1` is not.

### Step 2 — Query and condition

Select **SQLServer** as the data source. Write the T-SQL query that returns the metric you want to alert on. For PLE:

```sql
SELECT cntr_value AS PLE
FROM sys.dm_os_performance_counters
WHERE counter_name = 'Page life expectancy'
  AND object_name LIKE '%Buffer Manager%';
```

Set the time range to `10m to now` and format to `Table`. After clicking **Run query**, Grafana displays the result as a single row labeled `Series 1` with the current metric value — this confirms the query is returning data the alert engine can evaluate.

For the alert condition, set **WHEN Last OF QUERY** and choose the comparison:
- `Is below` → fires when the metric drops under a threshold (PLE, buffer hit rate, free space)
- `Is above` → fires when the metric exceeds a threshold (wait times, lock counts, active transactions)

Set the threshold value. For PLE, use `300`.

The **Preview alert rule condition** section at the bottom of Step 2 shows the current evaluation result:

```
Series 1    [current value]
─────────────────────────────
Series 1    0    Normal
```

`Series 1 = 0 / Normal` means the condition is not currently met — the alert would not fire right now. If the metric were breaching the threshold, it would show `Firing` instead. Use this preview to verify the query and condition are wired up correctly before saving.

### Step 3 — Folder and labels

Create a folder to organize your alert rules — one folder per category works well (`Query Performance`, `Server Health`, `Space`). Labels are optional but useful if you later want to route different alerts to different notification channels.

### Step 4 — Evaluation behavior

**Evaluation group** controls how often Grafana checks the condition. Create one group per category (e.g., `server-health`) and set the interval to `1m` for critical metrics, `5m` for slower-moving ones like space usage.

**Pending period** is the most important setting here. It defines how long the condition must be continuously met before the alert fires. Set it to `5m` for PLE — a brief dip during a backup does not warrant a page. Set it to `None` only for conditions where any breach is immediately actionable (e.g., a job failure).

**Keep firing for** controls the recovery delay. Leave it at `0s` unless you want to suppress flapping alerts that briefly clear and re-trigger.

### Step 5 — Notifications

Under **Contact point**, select the contact point configured in `alerts-and-notifiers.yml`. This is the email channel wired to your `GRAFANA_NOTIFICATION_ADDRESSES` from `.env`. The alert will fire an email when the condition is met and send a recovery email when it clears.

### Step 6 — Notification message

**Summary** appears in the email subject line — keep it short and specific:
> PLE on {{ $labels.instance }} dropped below 300

**Description** appears in the email body — use it to explain what the metric means and what to check first:
> Page Life Expectancy measures how long pages survive in the buffer pool. A sustained drop below 300 seconds indicates memory pressure. Check for new long-running queries, increased workload, or a recent change to `max server memory`.

**Runbook URL** is optional but valuable for on-call engineers who may not know the response steps.

---

Click **Save**. The rule is active immediately — no container restart required. For changes to the contact point or SMTP routing, edit `alerts-and-notifiers.yml` directly and restart Grafana:

```bash
docker-compose restart grafana
```

---

## The Two Dashboards

**sqlserver.json — Comprehensive:** 45+ panels covering every monitoring category. This is your full diagnostic view — use it during incident investigation or deep-dive analysis.

**sql_server_simplified.json — Simplified:** 30+ panels showing the essential metrics. This is your daily at-a-glance view — the panels you check every morning to confirm the server is healthy.

Both dashboards share the same data sources and queries. The simplified version collapses sections and removes the more granular panels to reduce visual noise.

---

## Dashboard Persistence

An important operational note: changes made directly in the Grafana UI to the provisioned dashboards are **not persisted** across container restarts. Grafana reads from the JSON files on startup and overwrites any in-memory changes.

The correct workflow for permanent dashboard changes:

1. Make your changes in the Grafana UI
2. Click **Dashboard Settings → JSON Model** to copy the updated JSON
3. Replace the content of `monitor/grafana/dashboards/sqlserver.json` (or the simplified file) with the new JSON
4. Commit the file

For alert changes, always edit `alerts-and-notifiers.yml` directly and restart Grafana — do not rely on UI-only changes.

---

## Common Issues and Fixes

**Datasource shows red / no data in panels**

Check `monitor/grafana/datasources.yml`. The `url` field for the MSSQL datasource must match the value of `DB_HOST` in your `.env`. Also verify `DB_USER` has `VIEW SERVER STATE` permission.

**Stack won't start**

Check whether port 3000 is already in use by another process. If so, change the port mapping in `docker-compose.yml`:

```yaml
ports:
  - "3001:3000"  # Use 3001 externally if 3000 is taken
```

Then access Grafana at `http://localhost:3001`.

**Email alerts not sending**

Gmail requires an App Password, not your main account password. Also verify that 2-Factor Authentication is enabled on the Google account. Check Grafana logs for SMTP errors:

```bash
docker-compose logs grafana | grep smtp
```

**Containers losing data after restart**

Check that Docker volumes are properly created:

```bash
docker volume ls | grep monitor
```

If volumes do not exist, the `docker-compose.yml` volume configuration needs review.

---

## Meet Your Agentic Monitor Assistant

The monitoring stack is straightforward to deploy — but troubleshooting it when something goes wrong means navigating Docker logs, YAML configuration files, Grafana's provisioning model, and SMTP settings simultaneously. Without knowing which file controls what, a "no data" panel can waste an hour.

The `/monitor` skill knows the stack's configuration by reading the actual files the moment you invoke it. It maps your symptom to the right component, shows you the exact fix, and can run Docker commands after your confirmation.

---

### A Real Scenario

You just deployed the stack. You open Grafana at `localhost:3000`, log in, and the dashboards show "No data" on every panel.

```
/monitor "Grafana is not showing any data on the dashboard"
```

The skill reads `docker-compose.yml`, `grafana/datasources.yml`, `grafana/grafana.ini`, and `monitor/README.md`. It responds:

> **Likely cause: SQL Server datasource misconfiguration.**
>
> I can see from `datasources.yml` that the MSSQL datasource is configured to connect to `${DB_HOST}` on port `${DB_PORT}` using `${DB_USER}` / `${DB_PASSWORD}` from your `.env` file.
>
> The most common reasons for "No data" after a fresh deployment:
>
> 1. **Wrong DB_HOST format** — The value should be `your_server_name,1433` (comma-separated port, not colon). Check your `.env` file.
> 2. **SQL Server not reachable from Docker** — Run `docker-compose logs grafana` to see if there are connection refused errors.
> 3. **User lacks VIEW SERVER STATE** — The monitoring user needs this permission to query the DMVs the dashboards use.
> 4. **Firewall blocking port 1433** — The Grafana container needs network access to your SQL Server.
>
> Let me check the Grafana logs first:
>
> ```bash
> docker-compose -f monitor/docker-compose.yml logs --tail=50 grafana
> ```
>
> Ready to run? (yes/no)

You type `yes`. The logs show `connection refused to 192.168.1.100:1433`. The skill continues:

> **Connection refused** confirms a network issue, not a credentials issue. The container cannot reach `192.168.1.100:1433`.
>
> Check:
> - Is SQL Server running and accepting connections on that IP and port?
> - Is a firewall rule blocking port 1433 from the Docker subnet?
> - Run `telnet 192.168.1.100 1433` from the Docker host to confirm connectivity.
>
> If SQL Server is running on the same machine as Docker, use `host.docker.internal` instead of `127.0.0.1` in your `.env` — Docker containers cannot reach the host via localhost.
>
> Update `DB_HOST=host.docker.internal,1433` in your `.env`, then restart Grafana:
>
> ```bash
> docker-compose -f monitor/docker-compose.yml restart grafana
> ```
>
> Ready to run? (yes/no)

From a blank "No data" dashboard to the exact fix in two exchanges — without reading a single configuration file manually.

---

### Invocation Examples

```
/monitor "Grafana is not showing any data on the dashboard"
/monitor "how do I configure Gmail SMTP for email alerts?"
/monitor "the stack won't start — getting a port conflict on 3000"
/monitor "what does the Page Life Expectancy panel measure and what is a healthy value?"
/monitor "restart the monitoring stack after changing datasources.yml"
/monitor "how do I add an alert that fires when PLE drops below 300?"
/monitor "update the SQL Server connection to a new server address"
/monitor "what panels are in the simplified dashboard vs. the comprehensive one?"
/monitor "my Grafana admin password from .env isn't working at login"
```

---

### How It Works Under the Hood

When you invoke `/monitor`, Claude reads these files immediately:

```
Read("monitor/docker-compose.yml")
Read("monitor/grafana/datasources.yml")
Read("monitor/grafana/grafana.ini")
Read("monitor/grafana/alerts-and-notifiers.yml")
Read("monitor/README.md")
```

For dashboard or panel questions, it also reads:

```
Read("monitor/grafana/dashboards/sqlserver.json")         — if needed
Glob("monitor/docs/*.md") → Read matching doc file
```

It then maps your issue to the right component:

| Your words | Focus | Files consulted |
|---|---|---|
| no data, blank panels, not showing | Datasource connection | `datasources.yml` |
| won't start, port conflict, container fails | Service config | `docker-compose.yml` |
| alert, email, SMTP, Gmail, notification | Alert routing + SMTP | `alerts-and-notifiers.yml` + `grafana.ini` |
| what does X panel mean, PLE, buffer, waits | Panel docs | matching `monitor/docs/*.md` |
| restart, update, stop, recreate | Docker Compose | `docker-compose.yml` |
| Azure SSO, OAuth, authentication | Auth config | `grafana.ini` |

**Security contract:** The skill will never read or display the contents of your `.env` file. It knows that file contains secrets. It references only the variable names (e.g., `DB_HOST`, `GRAFANA_SMTP_PASSWORD`) and explains what value format each expects.

**Docker command contract:** Every `docker-compose` command is shown to you before execution, with a plain-language explanation of what it will do. The skill never runs infrastructure commands silently.

---

### What This Changes

The monitoring stack has six configuration files that interact with each other. A "no data" problem could be in `datasources.yml`, the `.env`, the SQL Server firewall, the user's permissions, or the Docker network configuration. Previously, diagnosing it meant reading all six files and the logs in sequence.

The `/monitor` skill reads all the configuration files immediately and applies that context to your specific symptom — narrowing the diagnosis to two or three likely causes in seconds, showing the exact fix, and offering to run the corrective command.

It is the difference between "I need to look through the config" and "here is the line that is wrong and here is the fix."

---

*Data Eyes is an open-source SQL Server toolkit. The monitoring solution covered in this article lives in the [monitor/](https://github.com/lorenzouriel/data-eyes/tree/main/monitor) folder of the repository.*
