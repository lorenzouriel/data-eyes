# Real-Time SQL Server Monitoring with Grafana and Prometheus

You cannot fix what you cannot see.

Most SQL Server problems — slow queries, memory pressure, failed jobs, growing databases — do not announce themselves with an error message. They degrade gradually, quietly, until someone notices that something feels slow or a disk alarm fires at 2 AM.

The solution is visibility: a monitoring stack that watches your SQL Server continuously, surfaces problems before they become incidents, and gives you historical data to understand trends.

This article walks through a complete, containerized SQL Server monitoring solution built with **Grafana** and **Prometheus** — deployable in minutes, providing 45+ metrics out of the box, and configurable for email alerting.

---

## The Architecture

```
┌─────────────────────────────────────────────────────┐
│              Monitoring Solution                     │
└─────────────────────────────────────────────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     │                   │                   │
 ┌───▼────┐         ┌───▼────┐        ┌────▼─────┐
 │ Grafana│         │  MSSQL │        │Prometheus│
 │ :3000  │◄────────┤Database│        │  Backend │
 └────────┘         └────────┘        └──────────┘
     │
     ▼
 Email Alerts
 (SMTP/Gmail)
```

**Grafana** is the visualization layer. It connects directly to SQL Server as a data source and executes T-SQL queries to populate dashboard panels. It also handles alerting.

**Prometheus** is the time-series backend. It stores historical metric data so you can look at trends over time — not just the current state.

**Docker Compose** orchestrates both containers, manages volumes for data persistence, and wires together the configuration from environment variables.

There is no custom exporter to install, no agent on the SQL Server host, no middleware. Grafana queries SQL Server directly.

---

## What's Inside the Stack

```
monitor/
├── docker-compose.yml
├── .env                              # Credentials (not committed to git)
├── grafana/
│   ├── grafana.ini                   # Grafana instance configuration
│   ├── datasources.yml               # SQL Server + Prometheus connections
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

# Internal service URLs
PROMETHEUS_URL=http://prometheus:9090
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

Docker Compose pulls the Grafana and Prometheus images, creates persistent volumes, and starts both containers. Grafana reads the `grafana/` directory for its provisioned configuration — datasources, dashboards, and alert channels are all loaded automatically.

### Step 3: Verify

Open `http://localhost:3000` and log in with your admin credentials.

1. Navigate to **Configuration → Data Sources** — both SQLServer and Prometheus should show a green checkmark
2. Go to **Dashboards** and open the SQL Server dashboard
3. Confirm panels are displaying data

If datasources show red, check your `.env` values and verify SQL Server is reachable from the Docker network.

---

## What the Dashboards Monitor

### Server Health

The first section gives you the overview: how long has the server been up, how many active sessions are connected, and how many idle connections are sitting open.

Active sessions doing nothing still hold connections and may hold locks. A server with 300 idle sessions and 5 active ones has a connection pooling problem worth investigating.

### Query Performance

This section is where you spend most of your time during performance investigations:

- **Top 10 slowest queries** by average execution time
- **Query cache hit rate** — should be > 98% for OLTP workloads; a low rate means plans are being compiled too often
- **Queries per second** — your throughput baseline
- **Execution plan performance** — plan count and compilation rate

The underlying SQL queries read from `sys.dm_exec_query_stats` and `sys.dm_exec_sql_text`, giving you the actual query text alongside the performance numbers.

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

To add an alert to a panel:

1. Open a dashboard and click **Edit** on any panel
2. Go to the **Alert** tab
3. Define the condition (e.g., "PLE drops below 300 for 5 minutes")
4. Set the evaluation interval (e.g., every 1 minute)
5. Select the email contact point
6. Save the dashboard

The alert will fire an email when the condition is met and resolve (send a recovery email) when it clears.

For persistent alerts, you can also edit `alerts-and-notifiers.yml` directly and restart the Grafana container:

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
