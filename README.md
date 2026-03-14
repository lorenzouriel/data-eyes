<div align="center">
  <img src="monitor/docs/logos.png" alt="logo">
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
Data Eyes consists of three services that work together seamlessly:
```bash
┌─────────────────────────────────────────────────────────┐
│                  Data Eyes Ecosystem                    │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
    ┌───▼────┐       ┌────▼────┐      ┌────▼──────┐
    │Monitor │       │  Perf   │      │Maintenance│
    │(Watch) │       │(Analyze)│      │ (Automate)│
    └───┬────┘       └────┬────┘      └────┬──────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
              ┌───────────▼───────────┐
              │   SQL Server(s)       │
              │   - Databases         │
              │   - SQL Agent         │
              │   - DMVs & Logs       │
              └───────────────────────┘
```

### How They Work Together
**Typical Workflow:**
1. **Monitor** detects performance degradation (Grafana dashboard shows alert)
2. **Performance** toolkit analyzes root cause (wait stats, missing indexes, slow queries)
3. **Maintenance** automates ongoing fixes (index optimization, statistics updates, backups)
4. **Monitor** validates improvements (before/after baseline comparison)

**Example Scenario:**
- **Monitor** alerts: "Buffer pool hit rate dropped below 95%"
- **Performance** investigates: Wait statistics show memory pressure, Page Life Expectancy is low
- **Performance** recommends: Add indexes to reduce logical reads, optimize memory-intensive queries
- **Maintenance** executes: Automated index defragmentation and statistics update jobs
- **Monitor** confirms: Buffer pool hit rate returns to normal, queries run faster

## Components
### 1. Monitoring Solution (Grafana + Prometheus)
**Location:** [monitor/](monitor/)

**Purpose:** Real-time visibility and alerting for SQL Server health and performance

**What's Included:**
- **Grafana dashboards** - Pre-built visualizations with 45+ metrics
  - Comprehensive view (full server analysis)
  - Simplified view (essential metrics only)
- **Prometheus backend** - Time-series metrics storage with historical trending
- **Docker Compose stack** - Automated deployment and orchestration
- **Email alerting** - SMTP/Gmail integration for notifications
- **Pre-configured metrics:**
  - Server health: Uptime, sessions, connections
  - Query performance: Top 10 slowest queries, cache hit rate, latency
  - Resource utilization: Buffer pool, memory grants, Page Life Expectancy
  - Storage: Database sizes, transaction log usage, I/O statistics
  - SQL Agent jobs: Execution status, failures, history
  - Wait statistics: Performance bottleneck identification
  - Locks & blocking: Contention detection
  - Backup status: Last successful backup, backup types

**Key Features:**
- 2 fully provisioned Grafana dashboards
- Direct SQL Server connection (no exporter needed)
- Real-time and historical analysis
- Color-coded thresholds (green/yellow/red)
- Auto-refresh and time range selection
- Export to PDF/PNG for reporting
- Azure SSO configured and ready to be enabled

**Technologies:** Grafana (latest), Prometheus (latest), Docker, Microsoft SQL Server

### 2. Performance Tuning Toolkit

**Location:** [performance/](performance/)

**Purpose:** Systematic performance analysis and optimization methodology

**What's Included:**
- **Performance Tuning Workbook** (Excel) - Interactive planning and tracking
  - 9-step structured methodology
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
**9-Step Proven Approach** for measurable performance improvements
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

**Location:** [maintenance/](maintenance/)

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

**Location:** [sql-scripts/](sql-scripts/)

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
| `sql_maintenance/` | Maintenance playbooks and SQL Agent schedules |
| `sql_monitor/` | Grafana + Prometheus monitoring stack |
| `sql_profiler/` | SQL Profiler traces |
| `ssis/` | SSIS job scheduling and maintenance |
| `ssrs/` | SSRS report analysis and permission scripts |
| `triggers/` | Database triggers |

## Quick Start
### Prerequisites
- **SQL Server:** 2012+ (2016+ recommended for Query Store)
- **SQL Server Agent:** Running and enabled (for maintenance)
- **Docker:** 20.10+ with Docker Compose 2.0+ (for monitoring)
- **Permissions:** VIEW SERVER STATE, sysadmin for maintenance
- **Tools:** SSMS (SQL Server Management Studio), Microsoft Excel

### Installation Steps
#### 1. Set Up Monitoring (15 minutes)
```bash
cd monitor/
# Configure .env file with credentials

docker-compose up -d
# Access Grafana at http://localhost:3000
```

#### 2. Deploy Performance Toolkit (10 minutes)
```bash
cd performance/
# Open performance_tuning_workbook.xlsx
# Enable Query Store on target databases
# Run initial analysis scripts in SSMS
```

#### 3. Install Maintenance Solution (20 minutes)
```bash
cd maintenance/
# Download Ola Hallengren scripts from https://ola.hallengren.com/
# Execute MaintenanceSolution.sql in SSMS
# Create backup directory: mkdir C:\Backup
# Execute sql_agent_schedule_playbook.sql
# Verify 7 SQL Agent jobs are created
```

## Integration and Workflow
**Phase 1: Establish Baseline (Initial Setup)**
1. Deploy **Monitor** stack and verify dashboards show metrics
2. Open **Performance** workbook and capture baseline metrics
3. Deploy **Maintenance** jobs and verify first execution

**Phase 2: Continuous Operations (Ongoing)**
1. **Monitor** dashboards display real-time health (check daily)
2. **Maintenance** jobs run automatically per schedule (verify weekly)
3. **Performance** scripts run on-demand when investigating issues

**Phase 3: Performance Tuning (When Issues Arise)**
1. **Monitor** detects anomaly or alert fires
2. Use **Performance** methodology (Steps 0-9) to diagnose
3. Implement fixes (indexes, configuration, query tuning)
4. **Maintenance** automates ongoing optimization
5. **Monitor** validates improvements via baseline comparison

**Phase 4: Reporting and Trending (Monthly/Quarterly)**
1. Export **Monitor** dashboards to PDF for stakeholders
2. Review **Performance** workbook baseline log for trends
3. Analyze **Maintenance** CommandLog for operation history
4. Adjust schedules and thresholds as needed

## Documentation
Each component includes comprehensive documentation:

- **Monitor:** [monitor/README.md](monitor/README.md)
  - Architecture and component interaction
  - Dashboard features and panels
  - Alert configuration
  - Troubleshooting guide

- **Performance:** [performance/README.md](performance/README.md)
  - 9-step methodology detailed walkthrough
  - Script documentation (4 scripts × 4 guides)
  - Common performance scenarios
  - Best practices and thresholds

- **Maintenance:** [maintenance/README.md](maintenance/README.md)
  - Ola Hallengren script integration
  - Job scheduling and configuration
  - Use cases and examples (35+ scenarios)
  - Monitoring and logging queries

- **SQL Scripts:** [sql-scripts/README.md](sql-scripts/README.md)
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