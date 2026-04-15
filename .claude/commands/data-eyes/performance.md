---
name: performance
description: SQL Server performance tuning guide — maps symptoms to the 10-step methodology and runs diagnostic scripts
---

# /performance Command

> Systematic performance diagnosis using the Data Eyes 10-step methodology

## Usage

```
/performance <describe the symptom or investigation step>
```

## Examples

```
/performance "queries slowed down after the weekend, high CPU"
/performance "what is causing blocking on the server?"
/performance "I want to find missing indexes"
/performance "step 5 — analyze memory pressure"
/performance "plan regression after statistics update"
/performance "find unused indexes I can drop"
/performance "high wait statistics, not sure where to start"
/performance "run the full baseline — steps 0 through 1"
/performance "tempdb is hot, PAGELATCH waits on 2:1:1"
/performance "what MAXDOP and cost threshold should I set for an OLTP workload?"
```

---

## What This Skill Does

1. Reads the available performance diagnostic scripts and their documentation at invocation time
2. Maps your symptom to the correct step in the 10-step methodology
3. Explains which script(s) to run and what to look for in the output
4. Presents the SQL as a copy-paste block ready for SSMS
5. Offers optional execution via `sqlcmd` and interprets the live output

The full methodology and all 16 DMV scripts are documented in `articles/performance.md`. The workbook `performance/performance_tuning_workbook.xlsx` is the companion planning and tracking tool.

---

## The 10-Step Methodology

Data Eyes uses a proven, structured approach to SQL Server performance tuning:

```
Step 0: Prep         → Inventory environment, enable Query Store
Step 1: Baseline     → Wait stats, IO latency, file layout, PerfMon
Step 2: Workload     → Top CPU/read queries, missing/unused indexes, fragmentation
Step 3: Contention   → Blocking chains, deadlock XE session, RCSI check
Step 4: TempDB       → PAGELATCH contention on allocation pages
Step 5: Memory       → PLE, memory grants pending, buffer cache hit ratio
Step 6: CPU          → SOS_SCHEDULER_YIELD, CXPACKET, MAXDOP tuning
Step 7: I/O & Log    → PAGEIOLATCH, WRITELOG, file latency, log growth
Step 8: Config       → MAXDOP, cost threshold, max memory, DB options
Step 9: Verify       → Re-run baselines, compare before/after, log in Baseline_Log
```

**Key principle:** One change at a time. Measure before AND after every change. Log everything in the Baseline_Log.

---

## The 16 DMV Scripts

Scripts 01–16 are the diagnostic toolkit. They are inline in `articles/performance.md` and embedded in `performance_tuning_workbook.xlsx`.

| Script | Purpose | Step |
|---|---|---|
| 01_Server_Inventory | Edition, CPU count, NUMA, RAM | 0 |
| 02_Instance_Config | sys.configurations snapshot | 1 |
| 03_DB_Files_And_Autogrowth | File sizes, growth model | 1 |
| 04_Top_Waits | Top wait types (resource vs signal) | 1 |
| 05_IO_Latency_by_File | Avg read/write ms per file | 1 |
| 06_Top_Queries_By_CPU | Top 50 queries by total CPU | 2 |
| 07_Top_Queries_By_Reads | Top 50 queries by logical reads | 2 |
| 08_Missing_Indexes | Missing index candidates with impact score | 2 |
| 09_Index_Usage | Index seeks/scans/updates per index | 2 |
| 10_Index_Fragmentation | Fragmentation % + page count | 2 |
| 11_Active_Requests_Blocking | Blocking chains with query text | 3 |
| 12_Deadlocks_XE | Extended Events session for deadlocks (**write — confirm before running**) | 3 |
| 13_Enable_Query_Store | Enable Query Store on a database (**write — confirm before running**) | 0 |
| 14_Query_Store_Top | Top queries by avg CPU from Query Store | 2 |
| 15_RCSI_Check | Is Read Committed Snapshot Isolation enabled? | 3 |
| 16_Tempdb_Contention_Check | PAGELATCH waits on tempdb pages | 4 |

---

## Process

### Step 1: Read Available Scripts and Documentation

Use Glob to discover the scripts present in the repo:
```
Glob("performance/additional_queries/*.sql")
Glob("performance/additional_queries/docs/*.md")
```

Read all available scripts and their documentation files:
- `performance/additional_queries/wait_statistics.sql` + `docs/wait_statistics.md`
- `performance/additional_queries/missing_indexes.sql` + `docs/missing_indexes.md`
- `performance/additional_queries/unused_indexes.sql` + `docs/unused_indexes.md`
- `performance/additional_queries/update_statistics.sql` + `docs/update_statistics.md`

For scripts not yet present as `.sql` files (01–16 from the workbook), use the SQL inline in `articles/performance.md`. Read that file if needed.

### Step 2: Map Symptom to Methodology Step and Script

| Symptom / keyword | Step | Script(s) to use |
|---|---|---|
| slow queries, general degradation, not sure where to start | Step 1 | `04_Top_Waits` / `wait_statistics.sql` — start here always |
| workload, heavy queries, resource consumers, CPU, reads | Step 2 | `06_Top_Queries_By_CPU` + `07_Top_Queries_By_Reads` |
| blocking, contention, lock, sessions | Step 3 | `11_Active_Requests_Blocking` + `15_RCSI_Check` |
| deadlock, deadlock graph, XE, extended events | Step 3 | `12_Deadlocks_XE` |
| tempdb, version store, PAGELATCH, 2:1:1 | Step 4 | `16_Tempdb_Contention_Check` |
| memory, PLE, buffer pool, grants, out of memory | Step 5 | `04_Top_Waits` — look for RESOURCE_SEMAPHORE |
| CPU, high CPU, parallelism, MAXDOP, CXPACKET, SOS_SCHEDULER | Step 6 | `04_Top_Waits` + `06_Top_Queries_By_CPU` |
| I/O, disk, latency, reads, writes, PAGEIOLATCH | Step 7 | `05_IO_Latency_by_File` + `08_Missing_Indexes` |
| log, WRITELOG, log growth, log file | Step 7 | `03_DB_Files_And_Autogrowth` + `05_IO_Latency_by_File` |
| config, MAXDOP, cost threshold, max memory, ad hoc | Step 8 | `02_Instance_Config` |
| autogrowth, file size, percent growth, pre-size | Step 1/7 | `03_DB_Files_And_Autogrowth` |
| missing indexes, index impact, create index | Step 2 | `08_Missing_Indexes` / `missing_indexes.sql` |
| unused indexes, index cleanup, write overhead | Step 2 | `09_Index_Usage` / `unused_indexes.sql` |
| fragmentation, rebuild, reorganize | Step 2 | `10_Index_Fragmentation` |
| plan regression, query store, force plan, statistics | any | `14_Query_Store_Top` + `update_statistics.sql` |
| inventory, version, edition, NUMA, server info | Step 0 | `01_Server_Inventory` |
| query store enable, enable QS | Step 0 | `13_Enable_Query_Store` (**write — confirm first**) |
| verify, after fix, before/after, improvement | Step 9 | re-run `04_Top_Waits` + relevant baseline scripts |

### Step 3: Explain + Present

For each matched script:

1. State which methodology step this addresses and why
2. Show the SQL as a copy-paste block
3. Explain what to look for in the results:
   - Which columns are most important
   - What values indicate a problem (thresholds, red flags)
   - What action to take based on results

**Wait Statistics interpretation guide (04_Top_Waits):**

| Wait Type | Typical Cause | Next Step |
|---|---|---|
| `CXPACKET` / `CXCONSUMER` | Parallelism skew, low cost threshold | Step 6 — raise cost threshold, cap MAXDOP |
| `SOS_SCHEDULER_YIELD` | CPU saturation, hot code paths | Step 6 — tune top CPU queries |
| `PAGEIOLATCH_*` | Slow data file reads, large scans | Step 7 — improve indexes, check storage |
| `WRITELOG` | Log write bottleneck | Step 7 — pre-size log, fixed growth, faster disk |
| `LCK_M_*` | Blocking on locks | Step 3 — better indexes, shorter txns, RCSI |
| `PAGELATCH_*` (tempdb `2:*`) | TempDB allocation contention | Step 4 — add equal-size tempdb files |
| `ASYNC_NETWORK_IO` | App not consuming results fast enough | Fix app fetch pattern, reduce row size |
| `RESOURCE_SEMAPHORE` | Memory grant starvation | Step 5 — fix over-granting queries, update stats |
| `THREADPOOL` | Worker thread starvation | Reduce blocking, cap parallelism |

**Threshold guidance:**
- > 30% of total wait time = critical bottleneck, address immediately
- 10–30% = significant, investigate
- < 10% = monitor for trends

**Missing Indexes interpretation guide (08_Missing_Indexes):**
- `Avg_Estimated_Impact` = `avg_user_impact × (user_seeks + user_scans)` — higher is more impactful
- The generated `CREATE INDEX` statement is a recommendation — always check for similar existing indexes first
- Every index adds write overhead — do not create blindly on write-heavy tables
- One index at a time, then Step 9 (verify)

**Index Usage interpretation guide (09_Index_Usage):**
- Zero `user_seeks` + `user_scans` with high `user_updates` = pure write overhead, candidate for removal
- Stats reset on server restart — check `last_user_seek` before dropping anything

**IO Latency thresholds (05_IO_Latency_by_File):**
- Data files: < 10 ms good, 10–20 ms acceptable, > 20 ms poor
- Log files: < 5 ms good, 5–10 ms acceptable, > 10 ms poor

**Index Maintenance thresholds (10_Index_Fragmentation):**
- < 5% → do nothing
- 5–30% + page_count > 1000 → REORGANIZE + UPDATE STATISTICS (sampled)
- > 30% + page_count > 1000 → REBUILD (online if supported) + UPDATE STATISTICS (FULLSCAN for critical predicates)

### Step 4: Output

**Read-only scripts (01–11, 13 check queries, 14–16):**
1. Present the SQL as a copy-paste block
2. Explain what the results mean and what to do next
3. Ask: "Want me to run this via sqlcmd and interpret the output? (yes/no)"
4. If yes: check `$MSSQL_CONNECTION` environment variable
   - If set: run `sqlcmd $MSSQL_CONNECTION -Q "<script-content>"`
   - If not set: prompt — "Please provide: Server name, Username, Password"
5. After running, interpret the top results and recommend the next investigation step

**Write scripts (12_Deadlocks_XE, 13_Enable_Query_Store):**
- Explain exactly what will be created or changed
- Show the adapted SQL
- Write to `sql-scripts/generated/performance/<name>.sql` if file does not exist
- Ask: "Ready to execute? (yes/no)" — ONLY run after explicit yes

---

## Output Rules

- Present all read-only SQL as copy-paste blocks
- Offer sqlcmd execution for every script
- After execution, interpret results and name the next script to run
- For `CREATE INDEX` from missing_indexes results: treat as a write operation — show the statement, recommend non-production testing first, remind one-change-at-a-time
- For `12_Deadlocks_XE` and `13_Enable_Query_Store`: always confirm before executing

---

## Important Rules

- Scripts 01–11, 14–16 are read-only — they query DMVs and system views only
- Scripts 12 and 13 create objects on the server — ALWAYS confirm before running
- NEVER recommend creating or dropping indexes without telling the user to measure impact first (Step 9)
- Always remind the user: one change at a time, then Step 9 (verify), log in Baseline_Log
- If the user asks about the workbook (`performance_tuning_workbook.xlsx`), explain it is an Excel-based planning and tracking tool with tabs for Checklist, PerfMon_Counters, Index_Maintenance, Config_Review, and Baseline_Log — it complements the 16 DMV scripts
- Wait statistics are cumulative since last restart or `DBCC SQLPERF('sys.dm_os_wait_stats', CLEAR)` — advise the user if the data looks unexpectedly clean
