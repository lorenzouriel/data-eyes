---
name: performance
description: SQL Server performance tuning guide — maps symptoms to the 9-step methodology and runs diagnostic scripts
---

# /performance Command

> Systematic performance diagnosis using the Data Eyes 9-step methodology

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
```

---

## What This Skill Does

1. Reads the existing performance diagnostic scripts and their documentation at invocation time
2. Maps your symptom to the correct step in the 9-step methodology
3. Explains which script(s) to run and what to look for in the output
4. Presents the SQL as a copy-paste block ready for SSMS
5. Offers optional execution via `sqlcmd` and interprets the live output

---

## The 9-Step Methodology

Data Eyes uses a proven, structured approach to SQL Server performance tuning:

```
Step 0: Prep         → Establish environment, tools, permissions
Step 1: Baseline     → Capture current state metrics
Step 2: Workload     → Identify top resource consumers
Step 3: Contention   → Find blocking, locking, deadlocks
Step 4: TempDB       → Diagnose TempDB contention issues
Step 5: Memory       → Analyze PLE, buffer pool, memory grants
Step 6: CPU          → CPU pressure, parallelism, MAXDOP
Step 7: I/O & Log    → Disk latency, I/O stalls, log throughput
Step 8: Config       → Review MAXDOP, cost threshold, max memory
Step 9: Verify       → Measure improvements, before/after comparison
```

**Key principle:** One change at a time. Measure before AND after every change.

---

## Process

### Step 1: Read Performance Scripts and Documentation

Use Glob to discover all available scripts:
```
Glob("performance/additional_queries/*.sql")
Glob("performance/additional_queries/docs/*.md")
```

Read all 4 scripts and their corresponding documentation files:
- `performance/additional_queries/wait_statistics.sql` + `docs/wait_statistics.md`
- `performance/additional_queries/missing_indexes.sql` + `docs/missing_indexes.md`
- `performance/additional_queries/unused_indexes.sql` + `docs/unused_indexes.md`
- `performance/additional_queries/update_statistics.sql` + `docs/update_statistics.md`

### Step 2: Map Symptom to Methodology Step and Script

| Symptom / keyword | Step | Script(s) to use |
|---|---|---|
| slow queries, general degradation, not sure where to start | Step 1 | `wait_statistics.sql` — start here always |
| workload, heavy queries, resource consumers | Step 2 | `wait_statistics.sql` |
| blocking, contention, deadlock, lock | Step 3 | `wait_statistics.sql` — look for LOCK wait types |
| tempdb, version store, temp tables, PAGELATCH | Step 4 | `wait_statistics.sql` — look for PAGELATCH_* waits |
| memory, PLE, buffer pool, grants, out of memory | Step 5 | `wait_statistics.sql` — look for RESOURCE_SEMAPHORE waits |
| CPU, high CPU, parallelism, MAXDOP, CXPACKET | Step 6 | `wait_statistics.sql` + `missing_indexes.sql` |
| I/O, disk, latency, reads, writes, log | Step 7 | `missing_indexes.sql` + `unused_indexes.sql` |
| config, MAXDOP, cost threshold, max memory | Step 8 | `wait_statistics.sql` — identify bottleneck category first |
| verify, after fix, before/after, improvement | Step 9 | all scripts — run same queries as baseline for comparison |
| plan regression, execution plan changed, statistics | any | `update_statistics.sql` |
| missing indexes, index impact, create index | any | `missing_indexes.sql` |
| unused indexes, index cleanup, space savings | any | `unused_indexes.sql` |

### Step 3: Explain + Present

For each matched script:

1. State which methodology step this addresses and why
2. Show the SQL as a copy-paste block
3. Explain what to look for in the results:
   - Which columns are most important
   - What values indicate a problem (thresholds, red flags)
   - What action to take based on results
4. Reference the documentation file for deeper context

**Wait Statistics interpretation guide:**
- `CXPACKET` / `CXCONSUMER` → parallelism issues, review MAXDOP
- `LCK_M_*` → blocking/locking, check Step 3
- `PAGEIOLATCH_*` → I/O pressure, check indexes and disk
- `PAGELATCH_*` → TempDB contention, check Step 4
- `RESOURCE_SEMAPHORE` → memory grants, check Step 5
- `SOS_SCHEDULER_YIELD` → CPU pressure, check Step 6
- `WRITELOG` → log I/O bottleneck, check Step 7

**Missing Indexes interpretation guide:**
- Focus on `Avg_Estimated_Impact` column — higher is more impactful
- The generated `CREATE INDEX` statement is a recommendation, not a command — always review before creating
- Don't create all suggested indexes blindly; evaluate write overhead

**Unused Indexes interpretation guide:**
- Zero `user_seeks` + `user_scans` = candidate for removal
- High `user_updates` = this index is being maintained for writes but never read
- Always check index age — young indexes may not have enough data yet

### Step 4: Output

All performance scripts are read-only diagnostics — they do NOT modify data.

1. Present the SQL as a copy-paste block (no write-to-file needed for read-only queries)
2. Explain what the results mean and what to do next
3. Ask: "Want me to run this via sqlcmd and interpret the output? (yes/no)"
4. If yes: check `$MSSQL_CONNECTION` environment variable
   - If set: run `sqlcmd -S <server> -U <user> -P <pass> -Q "<script-content>"`
   - If not set: prompt — "Please provide: Server name, Username, Password"
5. After running, interpret the top results and recommend next steps

---

## Output Rules

**All scripts in performance/ are read-only:**
- Present SQL as copy-paste
- Explain output interpretation
- Offer sqlcmd execution
- After execution, interpret results and recommend the next investigation step

**If user asks about creating indexes based on missing_indexes.sql results:**
- This is a write operation — treat it like a destructive operation
- Show the `CREATE INDEX` statement
- Recommend testing on non-production first
- Remind: one index change at a time, measure before/after (Step 9)

---

## Important Rules

- All scripts in `performance/` are read-only — they query DMVs and system views only
- NEVER recommend creating or dropping indexes without telling the user to measure impact first
- Always remind the user: one change at a time, then Step 9 (verify)
- If the user asks about the workbook (`performance_tuning_workbook.xlsx`), explain it is an Excel-based planning and tracking tool covering all 9 steps — it complements the SQL scripts
- Wait statistics reset when SQL Server restarts — advise the user if the data looks unexpectedly clean
