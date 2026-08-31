# Performance Tuning

A comprehensive, structured approach to SQL Server performance tuning with methodology, analysis scripts, and an interactive workbook. This toolkit helps DBAs identify bottlenecks, optimize queries, and improve database performance through systematic analysis.

> Agent/machine-facing index: [`.claude/knowledge-base/_static/methodology.md`](../.claude/knowledge-base/_static/methodology.md) (compact step routing) and [`thresholds.yaml`](../.claude/knowledge-base/_static/thresholds.yaml) (canonical severity numbers — this README explains them, that file is the single source of truth for the actual values).

## Table of Contents
- [Overview](#overview)
- [What's Included](#whats-included)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Directory Structure](#directory-structure)
- [Performance Tuning Methodology](#performance-tuning-methodology)
- [Performance Workbook](#performance-workbook)

## Overview

This performance toolkit provides a **10-step structured methodology** for SQL Server performance tuning, following industry best practices:

**Core Principle:** *One change at a time, measure before & after.*

### Key Benefits

- ✓ Proven systematic approach to performance tuning
- ✓ Ready-to-use SQL analysis scripts with detailed documentation
- ✓ Interactive Excel workbook for tracking and planning
- ✓ Baseline-driven methodology for measurable improvements
- ✓ Covers all major performance areas (CPU, Memory, I/O, Indexes, Waits)
- ✓ Production-tested scripts from real-world scenarios

### Performance Categories Covered

1. **Indexing Strategy** - Missing and unused index identification
2. **Query Optimization** - Top CPU and I/O consuming queries
3. **Wait Statistics** - Bottleneck identification and analysis
4. **Statistics Management** - Staleness detection and updates
5. **Configuration Tuning** - MAXDOP, memory, parallelism settings
6. **TempDB Optimization** - Contention detection and resolution
7. **Memory Management** - Page Life Expectancy and memory grants
8. **I/O & Disk Performance** - Latency analysis and optimization

## What's Included

### 1. Performance Tuning Workbook
**File:** [performance_tuning_workbook.xlsx](performance_tuning_workbook.xlsx)

Interactive Excel workbook with tabs for:
- Performance methodology guide
- Server configuration tracking
- Index maintenance policies
- PerfMon counter guidance
- Configuration review checklists
- Baseline comparison logging

### 2. SQL Analysis Scripts
**Location:** [additional_queries/](additional_queries/)

Four core analysis scripts with comprehensive documentation:

| Script | Purpose | Documentation |
|--------|---------|---------------|
| [missing_indexes.sql](additional_queries/missing_indexes.sql) | Identify top 25 missing indexes by impact | [Docs](additional_queries/docs/missing_indexes.md) |
| [unused_indexes.sql](additional_queries/unused_indexes.sql) | Find top 25 unused indexes consuming resources | [Docs](additional_queries/docs/unused_indexes.md) |
| [wait_statistics.sql](additional_queries/wait_statistics.sql) | Analyze performance bottlenecks via waits | [Docs](additional_queries/docs/wait_statistics.md) |
| [update_statistics.sql](additional_queries/update_statistics.sql) | Identify stale statistics and update | [Docs](additional_queries/docs/update_statistics.md) |

### 3. Documentation
**Location:** [additional_queries/docs/](additional_queries/docs/)

Each script includes detailed documentation covering:
- Purpose and overview
- Output column descriptions
- Key features and capabilities
- Usage notes and warnings
- Best practices and thresholds
- Interpretation guidance

## Prerequisites

### SQL Server Requirements

- **Version:** SQL Server 2012+ (2016+ recommended for Query Store)
- **Edition:** Standard or Enterprise (some features require Enterprise)
- **Query Store:** Enable for historical query analysis (2016+)

### Permissions Required

```sql
-- Minimum permissions for running analysis scripts
GRANT VIEW SERVER STATE TO [YourUser];
GRANT VIEW DATABASE STATE TO [YourUser];

-- For comprehensive analysis
ALTER SERVER ROLE sysadmin ADD MEMBER [YourUser];
```

### Tools Needed

- **SQL Server Management Studio (SSMS)** - For executing scripts
- **Microsoft Excel** - For using the performance workbook
- **Performance Monitor (PerfMon)** - For collecting system counters
- **Extended Events** - For capturing deadlocks and wait events

## Quick Start

### 1. Enable Query Store (SQL Server 2016+)

```sql
-- Enable Query Store for query history tracking
ALTER DATABASE [YourDatabase] SET QUERY_STORE = ON;
ALTER DATABASE [YourDatabase] SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    INTERVAL_LENGTH_MINUTES = 60,
    MAX_STORAGE_SIZE_MB = 1000,
    QUERY_CAPTURE_MODE = AUTO,
    SIZE_BASED_CLEANUP_MODE = AUTO
);
```

### 2. Open Performance Workbook

Open [performance_tuning_workbook.xlsx](performance_tuning_workbook.xlsx) and review:
- **Methodology** tab - Understand the 10-step approach
- **PerfMon_Counters** tab - Set up performance counter collection
- **Baseline_Log** tab - Track your before/after measurements

### 3. Run Initial Analysis

Start with the most common bottleneck identifiers:

```sql
-- 1. Check what SQL Server is waiting on
-- Run: additional_queries/wait_statistics.sql

-- 2. Find missing indexes with high impact
-- Run: additional_queries/missing_indexes.sql

-- 3. Identify unused indexes wasting resources
-- Run: additional_queries/unused_indexes.sql

-- 4. Check for stale statistics
-- Run: additional_queries/update_statistics.sql
```

### 4. Follow the 10-Step Methodology

See [Performance Tuning Methodology](#performance-tuning-methodology) section below.

## Directory Structure

```bash
performance/
├── performance_tuning_workbook.xlsx    # Interactive Excel workbook (24 KB)
├── README.md                           # This file
└── additional_queries/                 # SQL analysis scripts
    ├── missing_indexes.sql             # Top 25 missing indexes
    ├── unused_indexes.sql              # Top 25 unused indexes
    ├── wait_statistics.sql             # Wait type analysis
    ├── update_statistics.sql           # Statistics management
    └── docs/                           # Script documentation
        ├── missing_indexes.md          # Missing indexes guide
        ├── unused_indexes.md           # Unused indexes guide
        ├── wait_statistics.md          # Wait statistics guide (162 lines)
        └── update_statistics.md        # Statistics management guide
```

## Performance Tuning Methodology

Follow this **10-step structured approach** for systematic performance improvements:

```bash
┌─────────────────────────────────────────────────────────┐
│           Performance Tuning Workflow                    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
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

### **Step 0 – Prep**

**Objective:** Document your environment and enable tracking

**Actions:**
1. **Server Inventory** - Document SQL Server version, edition, CPU, RAM
2. **Enable Query Store** (SQL Server 2016+):
   ```sql
   ALTER DATABASE [YourDatabase] SET QUERY_STORE = ON;
   ```

**Why?** You need to know what environment you're working with and have Query Store capturing queries for historical analysis.

**Tools:** Performance workbook, Query Store configuration

---

### **Step 1 – Baseline**

**Objective:** *Before changing anything, measure everything*

**Actions:**
1. **Capture Current State:**
   - Run instance configuration snapshot
   - Document database file sizes and autogrowth settings (should be fixed MB, not %)
   - Capture current wait statistics
   - Measure I/O latency by file

2. **Collect PerfMon Counters** for at least 24 hours (see workbook **PerfMon_Counters** tab):
   - Page Life Expectancy
   - Buffer Cache Hit Ratio
   - SQL Compilations/sec
   - Batch Requests/sec
   - Memory Grants Pending

**Why?** This becomes your "before" picture. Without it, you can't prove improvements or measure ROI.

**Scripts to Run:**
- [wait_statistics.sql](additional_queries/wait_statistics.sql) - Capture baseline waits

**Log results in:** Workbook **Baseline_Log** tab

---

### **Step 2 – Workload Analysis**

**Objective:** Find and optimize the worst-performing queries

**Actions:**
1. **Identify Top Resource Consumers:**
   - Top CPU-consuming queries
   - Top I/O-consuming queries (logical reads)
   - Longest-running queries

2. **Index Analysis:**
   - Review missing indexes (validate before creating - avoid duplicates)
   - Identify unused indexes consuming maintenance resources
   - Check index fragmentation levels

3. **Statistics Review:**
   - Find stale statistics (>30 days old with modifications)
   - Update outdated statistics

**Goal:** Reduce query cost through indexing, statistics updates, and query tuning.

**Scripts to Run:**
- [missing_indexes.sql](additional_queries/missing_indexes.sql) - Get CREATE INDEX statements
- [unused_indexes.sql](additional_queries/unused_indexes.sql) - Get DROP INDEX candidates
- [update_statistics.sql](additional_queries/update_statistics.sql) - Find and update stale stats

**Best Practice:** Apply the index maintenance policy from workbook **Index_Maintenance** tab.

---

### **Step 3 – Contention**

**Objective:** Eliminate blocking and deadlocks

**Actions:**
1. **Monitor Active Blocking:**
   - Identify which sessions are blocking others
   - Track wait time and blocking chains
   - Review blocking patterns

2. **Capture Deadlocks:**
   - Set up Extended Events to track deadlock graphs
   - Analyze victim queries and resources involved
   - Implement deadlock prevention strategies

**Goal:** Keep concurrency smooth by removing hotspots and serialization points.

**Common Solutions:**
- Add missing indexes to reduce lock duration
- Review transaction isolation levels
- Implement optimistic concurrency where appropriate
- Reduce transaction scope and duration

---

### **Step 4 – TempDB**

**Objective:** Optimize TempDB for high-concurrency workloads

**Actions:**
1. **Check for PAGELATCH Waits:**
   - Look for PAGELATCH_UP on allocation pages
   - Indicates allocation contention in TempDB

2. **Optimize TempDB Configuration:**
   - Add more TempDB data files (1 per logical CPU up to 8 is common)
   - All files should be equal size and same autogrowth settings
   - Place on fast storage (SSD recommended)

**Wait Types to Monitor:**
- `PAGELATCH_UP` - Allocation page contention
- `PAGELATCH_EX` - Page update contention

**Reference:** Workbook **Config_Review** tab for TempDB best practices

---

### **Step 5 – Memory**

**Objective:** Ensure adequate memory allocation and detect pressure

**Actions:**
1. **Monitor Key Metrics:**
   - **Page Life Expectancy (PLE)** - Should be >300 seconds (5 minutes)
   - **Memory Grants Pending** - Should be 0 or very low
   - **Buffer Cache Hit Ratio** - Should be >95%

2. **Investigate Memory Pressure:**
   - If PLE drops consistently → memory pressure
   - If Memory Grants Pending > 0 sustained → queries need more memory
   - Review memory-intensive queries

**Common Solutions:**
- Add more RAM to server
- Optimize queries to reduce memory grants
- Review max server memory setting
- Identify and fix memory leaks

**PerfMon Counters:** See workbook **PerfMon_Counters** tab

---

### **Step 6 – CPU**

**Objective:** Optimize CPU utilization and parallelism

**Actions:**
1. **Identify CPU Pressure:**
   - High `SOS_SCHEDULER_YIELD` waits
   - Sustained CPU > 80%
   - Long scheduler wait times

2. **Optimization Strategies:**
   - Tune top CPU-consuming queries
   - Review and adjust **MAXDOP** (Max Degree of Parallelism)
   - Adjust **Cost Threshold for Parallelism** (default 5 is too low, try 25-50)
   - Review parallelism waits (CXPACKET, CXCONSUMER)

**Configuration Guidelines:**
- **MAXDOP:** Number of logical processors, up to 8 (or per-NUMA node)
- **Cost Threshold:** 25-50 for OLTP, 5-10 for analytics

**Reference:** Workbook **Config_Review** tab

---

### **Step 7 – I/O / Log**

**Objective:** Optimize disk I/O and transaction log performance

**Actions:**
1. **Identify I/O Bottlenecks:**
   - High `PAGEIOLATCH_*` waits → slow data file reads
   - High `WRITELOG` waits → transaction log bottleneck
   - High disk latency (>15ms for data, >5ms for logs)

2. **Optimization Strategies:**
   - Add missing indexes to reduce logical reads
   - Upgrade to faster storage (SSD/NVMe)
   - Pre-size data and log files to avoid autogrowth
   - Separate data and log files on different physical disks
   - Review I/O-intensive queries

**Latency Thresholds:**
- **Data Files:** <10ms good, 10-20ms acceptable, >20ms poor
- **Log Files:** <5ms good, 5-10ms acceptable, >10ms poor

**Wait Types:**
- `PAGEIOLATCH_SH` - Read waits
- `PAGEIOLATCH_EX` - Write waits
- `WRITELOG` - Transaction log write waits

---

### **Step 8 – Config Review**

**Objective:** Validate configuration against best practices

**Frequency:** Quarterly or after major changes

**Actions:**
Review settings in workbook **Config_Review** tab:
- **MAXDOP** - Parallelism control
- **Cost Threshold for Parallelism** - When to use parallel plans
- **Max Server Memory** - SQL Server memory limit
- **Optimize for Ad Hoc Workloads** - Enable for OLTP workloads
- **TempDB Files** - Proper count and sizing
- **Database Autogrowth** - Fixed MB increments, not percentages
- **Backup Compression** - Enable to reduce backup size/time

**Tools:** sp_configure, sys.configurations DMV

---

### **Step 9 – Verify**

**Objective:** Measure improvements and validate changes

**Actions:**
1. **Rerun Baseline Steps:**
   - Capture wait statistics again
   - Measure I/O latency
   - Collect PerfMon counters
   - Review top queries

2. **Compare Before vs. After:**
   - Log results in workbook **Baseline_Log** tab
   - Calculate percentage improvements
   - Document changes made

3. **Validate Success:**
   - Wait times reduced?
   - Query execution times improved?
   - I/O latency decreased?
   - CPU utilization more consistent?

**Rule:** **One change at a time, measure before & after.**

---

### Workflow Summary

**Complete Journey:**
```
Prep → Baseline → Workload → Contention → TempDB → Memory → CPU → I/O → Config → Verify
```

**Time Investment:**
- Initial baseline: 2-4 hours
- Analysis: 4-8 hours
- Implementation: Varies by changes
- Verification: 2-4 hours

**Expected Outcome:** 20-50% performance improvement in most cases

## Performance Workbook

**File:** [performance_tuning_workbook.xlsx](performance_tuning_workbook.xlsx)

The interactive Excel workbook contains multiple tabs for planning, tracking, and documenting your performance tuning efforts.

### Workbook Tabs

1. **Methodology** - Step-by-step tuning workflow (Steps 0-9)
2. **PerfMon_Counters** - Key performance counters to collect
3. **Index_Maintenance** - Fragmentation thresholds and rebuild/reorg policy
4. **Config_Review** - Best practice configuration checklist
5. **Baseline_Log** - Before/after comparison tracking

### How to Use the Workbook

1. **Start with Methodology Tab**
   - Review the 10-step process
   - Understand the systematic approach

2. **Configure PerfMon Collection**
   - Use PerfMon_Counters tab to set up monitoring
   - Collect data for 24 hours minimum
   - Track trends over time

3. **Log Your Baseline**
   - Record initial metrics in Baseline_Log
   - Document configuration settings
   - Capture wait statistics and query performance

4. **Review Index Policy**
   - Use Index_Maintenance tab guidelines:
     - <5% fragmentation: No action
     - 5-30% fragmentation: REORGANIZE
     - >30% fragmentation: REBUILD

5. **Check Configuration**
   - Review Config_Review checklist quarterly
   - Validate MAXDOP, memory, and parallelism settings
   - Document any deviations from best practices

6. **Track Changes**
   - Log all changes made
   - Record before/after metrics
   - Calculate improvement percentages