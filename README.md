<div align="center">
  <img src="assets/logo.svg" alt="Data Eyes logo" width="180">
</div>

# SQL Server Monitoring, Performance & Maintenance Toolkit

[![GitHub stars](https://img.shields.io/github/stars/lorenzouriel/data-eyes?style=social)](https://github.com/lorenzouriel/data-eyes/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/lorenzouriel/data-eyes?style=social)](https://github.com/lorenzouriel/data-eyes/network/members)
[![GitHub issues](https://img.shields.io/github/issues/lorenzouriel/data-eyes)](https://github.com/lorenzouriel/data-eyes/issues)
[![GitHub release](https://img.shields.io/github/v/release/lorenzouriel/data-eyes)](https://github.com/lorenzouriel/data-eyes/releases)

**Data Eyes** is an open-source, solution that delivers *complete visibility* and *best-practice automation* for Microsoft SQL Server environments.

It combines real-time monitoring, systematic performance tuning, and automated maintenance in a single integrated toolkit. Designed for DBAs, developers, and operations teams managing SQL Server databases.

## What Problem Does It Solve?
Managing SQL Server effectively requires three critical capabilities:
1. **Visibility**: Knowing what's happening right now (monitoring)
2. **Analysis**: Understanding performance issues and how to fix them (tuning)
3. **Automation**: Ensuring consistent operational excellence (maintenance)

## Architecture Overview
The **dashboard is the main service** — start there. Performance and Maintenance are standalone toolkits it works alongside; `.claude/` and `mcp/` are secondary, agent-only tooling for working on this repo with Claude Code, not something you need to run the dashboard:
```bash
┌─────────────────────────────────────────────────────────┐
│                  Data Eyes Ecosystem                     │
└─────────────────────────────────────────────────────────┘

  PRIMARY — start here
  ┌────────────────────────────────────────────────────┐
  │                     Dashboard                        │
  │             (Watch — connects directly)               │
  └───────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              │                         │
        ┌─────▼─────┐             ┌─────▼──────┐
        │    Perf    │             │ Maintenance │
        │  (Analyze) │             │ (Automate)  │
        └─────┬──────┘             └──────┬──────┘
              │                           │
              └─────────────┬─────────────┘
                             │
                  ┌──────────▼──────────┐
                  │    SQL Server(s)     │
                  │  Databases · Agent   │
                  │  DMVs & Logs         │
                  └──────────────────────┘

  SECONDARY — agent tooling, not required to run the dashboard
  ┌────────────────────────────────────────────────────┐
  │  .claude/   commands, agents, knowledge base           │
  │       │ names an MCP tool / reads _static/ for routing │
  │       ▼                                                │
  │  mcp/   data-eyes-mcp — read access to SQL Server(s)   │
  │         (used by Claude Code only, not the dashboard)  │
  └────────────────────────────────────────────────────┘
```

### How They Work Together
**Typical Workflow:**
1. **Dashboard** detects performance degradation (fleet health rollup shows Warning/Critical)
2. **Performance** toolkit analyzes root cause (wait stats, missing indexes, slow queries)
3. **Maintenance** automates ongoing fixes (index optimization, statistics updates, backups)
4. **Dashboard** validates improvements (before/after trend comparison)

**Example Scenario:**
- **Dashboard** alerts: category severity flips to Warning on the Index & Buffer tab
- **Performance** investigates: Wait statistics show memory pressure, Page Life Expectancy is low
- **Performance** recommends: Add indexes to reduce logical reads, optimize memory-intensive queries
- **Maintenance** executes: Automated index defragmentation and statistics update jobs
- **Dashboard** confirms: severity returns to OK, trend strip shows the recovery

## Components
### 1. Dashboard App (custom, connects directly to SQL Server)
**Location:** [dashboard/](dashboard/)

**Purpose:** Real-time visibility and evaluated health status for SQL Server fleets — a DPA-style Fleet Status page and per-instance drill-down, not a generic panel dashboard

**What's Included:**
- **Fleet Status** - Fleet-wide health rollup (OK/Warning/Critical per instance and category), table and tile views with a live wait-time sparkline per row
- **Per-instance drill-down** - Wait types, Blocking, Sessions & users, SQL statements (with real execution-plan time attribution), Resources, and Advisor
- **Advisor** - On-demand, Claude-drafted root-cause findings over real diagnostic data (wait history, blocking chain, top query + plan, missing-index candidates) — never a fabricated "tested" or "modelled" claim, just a labeled estimate
- **Ask the fleet** - Real multi-turn chat over the fleet's live health data
- **Database-backed instance registry** - Self-service "Register instance" in the Admin panel; `instances.yaml` only seeds it once on first boot
- **Real user accounts** - One shared team, admin/member roles, no more single shared credential
- **Trend history** - The dashboard's own Postgres database + persistent collector, independent of any monitored SQL Server
- **Docker Compose stack** - `dashboard/docker-compose.yml`

**Key Features:**
- Real evaluated alerting (worst-of-category/instance/fleet severity rollup), not just static color thresholds
- Talks directly to each monitored SQL Server — no MCP hop in the rendering/collection path (see `dashboard/README.md`'s "Why not MCP for the dashboard itself?")
- Trend strips per category, backed by the dashboard's own database
- Graceful degradation: the insights agent is fully optional and no-ops cleanly when unconfigured (the database itself, unlike earlier versions of this dashboard, is required — it backs login and the instance registry too, not just trend charts)

**Technologies:** FastAPI, React + TypeScript, PostgreSQL, Docker, Microsoft SQL Server (direct connection, `pyodbc`)

Separately, [`mcp/`](mcp/) runs its own `data-eyes-mcp` server for **agent use only** — Claude Code's `sql-server-dba` agent, not the dashboard (see the Documentation section below).

> The previous Grafana + Prometheus stack (`monitor/`) has been retired now that every panel category it covered has a live equivalent here — see `.claude/knowledge-base/_static/taxonomy.md` for the full mapping.

### 2. Performance Tuning Toolkit

**Location:** [.claude/resources/performance/](.claude/resources/performance/)

**Purpose:** Systematic performance analysis and optimization methodology

**What's Included:**
- **Performance Tuning Workbook** (Excel) - Interactive planning and tracking
  - 10-step structured methodology
  - PerfMon counter guidance
  - Baseline comparison logging
  - Index maintenance policy templates
  - Configuration review checklists
- **SQL Analysis Scripts** - Production-ready diagnostic queries
  - `missing_indexes.sql` - Top 25 missing indexes by impact score
  - `unused_indexes.sql` - Top 25 unused indexes consuming resources
  - `wait_statistics.sql` - Bottleneck identification via wait analysis
  - `update_statistics.sql` - Stale statistics detection and update
- **Comprehensive Documentation** - Detailed guides for each script
  - Query explanations and use cases
  - Output interpretation guidance
  - Best practices and thresholds
  - Warning notes and considerations

**Core Methodology:**
**10-Step Proven Approach** for measurable performance improvements
```bash
Step 0: Prep → Step 1: Baseline → Step 2: Workload Analysis
    │               │                       │
    ▼               ▼                       ▼
Step 3: Contention → Step 4: TempDB → Step 5: Memory
    │                    │                  │
    ▼                    ▼                  ▼
Step 6: CPU → Step 7: I/O/Log → Step 8: Config Review
    │             │                    │
    └─────────────┴────────────────────┘
                   │
                   ▼
              Step 9: Verify
```

**Key Principle:** *One change at a time, measure before & after.*

**Performance Categories Covered:**
- Indexing strategy (missing and unused indexes)
- Query optimization (CPU and I/O consumers)
- Wait statistics analysis (bottleneck identification)
- Statistics management (staleness detection)
- Configuration tuning (MAXDOP, memory, parallelism)
- TempDB optimization (contention resolution)
- Memory management (PLE, memory grants)
- I/O & disk performance (latency optimization)

**Expected Outcome:** 20-50% performance improvement in most cases

### 3. Maintenance Automation

**Location:** [.claude/resources/maintenance/](.claude/resources/maintenance/)

**Purpose:** Automated operational tasks for data protection and performance consistency

**What's Included:**
- **Maintenance Playbook** (`playbook.sql`) - Core maintenance routines
  - Full database backups (daily)
  - Differential backups (every 12 hours)
  - Transaction log backups (every 30 minutes)
  - Integrity checks (weekly fast, monthly comprehensive)
  - Index optimization (weekly defragmentation)
  - Statistics updates (weekly on modified objects)
- **SQL Agent Job Scheduler** (`sql_agent_schedule_playbook.sql`) - 7 pre-configured jobs
- **Use Case Examples** - Advanced scenarios and configurations
  - 15 backup scenarios (local, network, Azure, AWS, encrypted)
  - 10 integrity check scenarios (CHECKDB, CHECKALLOC, filegroups)
  - 10 index optimization scenarios (rebuild, reorganize, partitions)

**Based on Ola Hallengren's Industry-Standard Scripts:**
Trusted by enterprises worldwide, battle-tested in production

**Scheduled Automation:**
| Time | Job | Purpose |
|------|-----|---------|
| 01:00 AM (Saturday) | Index Optimization | Defragmentation and rebuild |
| 02:00 AM (Daily) | Full Backup | Complete database backup |
| 03:00 AM (Sunday) | Integrity Check | CHECKDB corruption detection |
| 04:00 AM (Saturday) | Statistics Update | Query optimizer stats refresh |
| 06:00 AM & 06:00 PM | Differential Backup | Changes since last full backup |
| Every 30 minutes | Transaction Log Backup | Point-in-time recovery capability |

**Key Features:**
- Zero external dependencies (SQL Agent only)
- Automated backup verification with checksums
- 7-day retention policy (configurable)
- Comprehensive logging to CommandLog table
- Email notifications on failures
- Parallel execution for multiple databases
- Online operations support (Enterprise Edition)
- Azure/AWS/network share compatibility

**Data Protection:**
- **RPO (Recovery Point Objective):** 30 minutes (with log backups)
- **RTO (Recovery Time Objective):** Depends on backup size
- **Backup compression:** 50-60% space savings
- **Integrity validation:** Weekly fast + monthly comprehensive checks

### 4. SQL Scripts Collection

**Location:** [.claude/resources/sql-scripts/](.claude/resources/sql-scripts/)

**Purpose:** Personal collection of reusable SQL Server scripts organized by topic

**What's Included:**
| Folder | Purpose |
|--------|---------|
| `audit/` | Auditing SQL Server activities |
| `backup_recovery/` | Backup, recovery model, and restore scripts |
| `custom_alert_emails/` | Database Mail and custom job alert emails |
| `database_size/` | Monitor database and file sizes |
| `free_space/` | Disk and filegroup free space queries |
| `functions/` | Custom SQL functions |
| `helps/` | Helper scripts, templates, and spatial data examples |
| `index/` | Index creation, fragmentation checks, and rebuild scripts |
| `lock/` | Blocking session reports and lock monitoring |
| `query_store/` | Query Store configuration and analysis |
| `server/` | Linked servers, server info, and role queries |
| `sql_access/` | User management, permissions, and access auditing |
| `sql_agent/` | SQL Agent job monitoring, access, and history |
| `sql_docker/` | Docker Compose setup for SQL Server |
| `sql_profiler/` | SQL Profiler traces |
| `ssis/` | SSIS job scheduling and maintenance |
| `ssrs/` | SSRS report analysis and permission scripts |
| `triggers/` | Database triggers |

### 5. Claude Code Integration (secondary — supports the toolkit, doesn't run it)

**Location:** [.claude/](.claude/)

**Purpose:** Makes this repo usable with Claude Code — slash commands, specialist agents, and a knowledge-base layer that keeps severity thresholds, naming rules, and script routing in one place instead of duplicated across docs

**What's Included:**
- **Commands** (`.claude/commands/data-eyes/`) - `/sql-performance`, `/sql-maintenance`, `/sql-scripts`, `/sql-kb`, `/sql-pr-review`, `/sql-monitor`, `/sql-visual-report`, and more
- **Agents** (`.claude/agents/`) - `sql-server-dba` (troubleshooting, tuning, maintenance via live `data-eyes-mcp` tools or the script folders as fallback) and `dashboard-app` (diagnoses the dashboard stack itself)
- **Knowledge base** (`.claude/knowledge-base/`) - `_static/` is the compact, cross-cutting index (severity thresholds, category/tab/script routing, naming rules, the 10-step methodology, a script catalog) that both agents and the dashboard's severity logic read from; per-database `.md` files (built by `/sql-kb`) hold deep per-instance data. See `.claude/knowledge-base/README.md`.
- **Resources** (`.claude/resources/`) - the Performance, Maintenance, and SQL Scripts toolkits described below live here, not at the repo root — see their own sections for what each contains

Not required to run the dashboard — the maintenance/performance scripts still work exactly as documented in their own READMEs by hand, they're just addressed under `.claude/resources/` now, not the repo root. This is the layer that lets Claude Code work on this repo, or drive it on your behalf, consistently.

## Quick Start
### Prerequisites
- **SQL Server:** 2012+ (2016+ recommended for Query Store)
- **SQL Server Agent:** Running and enabled (for maintenance)
- **Docker:** 20.10+ with Docker Compose 2.0+ (for the dashboard app; optional for `mcp/`, agent-only)
- **Permissions:** VIEW SERVER STATE, sysadmin for maintenance
- **Tools:** SSMS (SQL Server Management Studio), Microsoft Excel

### Installation Steps
#### 1. Set Up the Dashboard App (15 minutes)
```bash
# Postgres first — the dashboard's own database (required: trend history,
# instance registry, and login all live here). See dashboard/README.md.
docker run -d --name data-eyes-dashboard-repo -p 5432:5432 \
  -e POSTGRES_DB=data_eyes_dashboard -e POSTGRES_USER=data_eyes -e POSTGRES_PASSWORD=change-me \
  -v "$(pwd)/dashboard/repository/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  postgres:16-alpine

cd dashboard/backend
cp .env.example .env
# set DASHBOARD_ADMIN_PASSWORD, SESSION_SECRET_KEY, REPOSITORY_DSN, and INSTANCE_SECRET_KEY
uv run --with-editable . uvicorn app.main:app --reload --port 8090
# Access the dashboard frontend per dashboard/README.md's quick start —
# instances and additional user logins are added through the UI, not files
```

(Optional, agent-only — not needed to run the dashboard: `mcp/` gives Claude Code live SQL Server access. See `mcp/README.md`.)

#### 2. Deploy Performance Toolkit (10 minutes)
```bash
cd .claude/resources/performance/
# Open performance_tuning_workbook.xlsx
# Enable Query Store on target databases
# Run initial analysis scripts in SSMS
```

#### 3. Install Maintenance Solution (20 minutes)
```bash
cd .claude/resources/maintenance/
# Download Ola Hallengren scripts from https://ola.hallengren.com/
# Execute MaintenanceSolution.sql in SSMS
# Create backup directory: mkdir C:\Backup
# Execute sql_agent_schedule_playbook.sql
# Verify 7 SQL Agent jobs are created
```

## Integration and Workflow
**Phase 1: Establish Baseline (Initial Setup)**
1. Deploy the **Dashboard** app and verify fleet health shows OK
2. Open **Performance** workbook and capture baseline metrics
3. Deploy **Maintenance** jobs and verify first execution

**Phase 2: Continuous Operations (Ongoing)**
1. **Dashboard** displays real-time fleet health (check daily)
2. **Maintenance** jobs run automatically per schedule (verify weekly)
3. **Performance** scripts run on-demand when investigating issues

**Phase 3: Performance Tuning (When Issues Arise)**
1. **Dashboard** detects a severity change (insights feed, or a tab turns Warning/Critical)
2. Use **Performance** methodology (Steps 0-9) to diagnose
3. Implement fixes (indexes, configuration, query tuning)
4. **Maintenance** automates ongoing optimization
5. **Dashboard** validates improvements via trend strip comparison

**Phase 4: Reporting and Trending (Monthly/Quarterly)**
1. Review **Dashboard** trend strips for stakeholders, or generate a report with `/sql-visual-report`
2. Review **Performance** workbook baseline log for trends
3. Analyze **Maintenance** CommandLog for operation history
4. Adjust schedules and thresholds as needed

## Documentation
Each component includes comprehensive documentation:

- **Dashboard:** [dashboard/README.md](dashboard/README.md)
  - Architecture, quick start, and Docker Compose setup
  - Instance registry, user accounts, trend history, and embedded insights agent configuration
  - Health rollup

- **MCP:** [mcp/README.md](mcp/README.md)
  - `data-eyes-mcp` server setup (stdio + HTTP transports) — agent-only, not used by the dashboard
  - Available diagnostic tools, plus the dashboard-repository trend tools (optional)

- **Performance:** [.claude/resources/performance/README.md](.claude/resources/performance/README.md)
  - 10-step methodology detailed walkthrough
  - Script documentation (4 scripts × 4 guides)
  - Common performance scenarios
  - Best practices and thresholds

- **Maintenance:** [.claude/resources/maintenance/README.md](.claude/resources/maintenance/README.md)
  - Ola Hallengren script integration
  - Job scheduling and configuration
  - Use cases and examples (35+ scenarios)
  - Monitoring and logging queries

- **SQL Scripts:** [.claude/resources/sql-scripts/README.md](.claude/resources/sql-scripts/README.md)
  - Personal collection of reusable SQL Server scripts
  - Organized by topic (audit, backup, index, access, agent, etc.)
  - Quick reference for day-to-day DBA tasks

## Contributing
Contributions are welcome! To contribute:
1. Test changes in non-production environment
2. Document new features or scripts
3. Update relevant README files
4. Ensure backward compatibility

## License
This project integrates several open-source components:
- **Grafana:** Apache License 2.0
- **Prometheus:** Apache License 2.0
- **Ola Hallengren Maintenance Solution:** Free for all usage

Data Eyes configuration and integration is provided as-is for the community.

## Support
| Type                | Where                            |
| ------------------- | -------------------------------- |
| Documentation       | Component README files           |
| Open a Question     | GitHub Discussions               |
| Troubleshooting     | Example SQL queries, logs        |
| Help                | [Book a 30 min call](https://calendly.com/lorenzouriel394/30min)  |


---

> **Welcome to Data Eyes!** 🧿