## **Step 0 – Prep**
* **Inventory**: Run the script `01_Server_Inventory` → this documents your SQL Server version, edition, CPU, RAM.
* **Enable Query Store**: If you’re on SQL Server 2016+ (or Azure Managed Instance), enable it using script `13_Enable_Query_Store`. This gives you query history for tuning.

*Why?* You need to know what environment you’re working with and have Query Store capturing queries.

## **Step 1 – Baseline**
The idea here is: *before changing anything, measure everything*.
1. Run:
   * `02_Instance_Config` → snapshot server configuration.
   * `03_DB_Files_And_Autogrowth` → check database file sizes and autogrowth (should be fixed MB, not %).
   * `04_Top_Waits` → capture waits (what SQL Server is waiting on).
   * `05_IO_Latency_by_File` → check disk performance by file.
2. Collect PerfMon counters for at least 24h (see **PerfMon_Counters** tab).

*Why?* This becomes your “before” picture. Without it, you can’t prove improvements.

## **Step 2 – Workload Analysis**
This is where you find **the worst queries**:
* Run `06_Top_Queries_By_CPU` and `07_Top_Queries_By_Reads`.
* Look at missing indexes (`08_Missing_Indexes`) but don’t just apply blindly—validate they’re not duplicates.
* Check index usage (`09_Index_Usage`) to find unused but costly indexes.
* Measure fragmentation (`10_Index_Fragmentation`) and apply the policy in **Index_Maintenance** tab.

*Goal:* Reduce query cost with indexing, stats, and query tuning.

## **Step 3 – Contention**
When workloads block each other:
* `11_Active_Requests_Blocking` → see who’s blocking who.
* `12_Deadlocks_XE` → set up Extended Events to capture deadlocks.

*Goal:* Keep concurrency smooth by removing hotspots.

## **Step 4 – TempDB**
Run `16_Tempdb_Contention_Check`.
* If you see **PAGELATCH waits**, add more TempDB data files (1 file per logical CPU up to 8 is common).

## **Step 5 – Memory**
* Watch PerfMon: `Page life expectancy` and `Memory Grants Pending`.
* If grants > 0 for sustained time → queries are asking for too much memory, or you don’t have enough.

## **Step 6 – CPU**
* High `SOS_SCHEDULER_YIELD` waits or sustained CPU > 80%?
  * Tune the top CPU queries.
  * Adjust **MAXDOP** and **Cost Threshold for Parallelism** (see **Config_Review** tab).

## **Step 7 – IO / Log**
* High `PAGEIOLATCH` → slow reads (need indexes or faster storage).
* High `WRITELOG` → transaction log bottleneck. Fix with pre-sizing log files and faster log disks.

## **Step 8 – Config Review**
Quarterly, review settings against best practices:
* MAXDOP, cost threshold, memory, ad-hoc optimization, tempdb files, etc.

## **Step 9 – Verify**
* Rerun all baseline steps after changes.
* Compare before vs after in **Baseline_Log**.
*Rule*: **One change at a time, measure before & after.**

So, that’s the structured journey:
**Prep → Baseline → Workload → Contention → TempDB → Memory → CPU → IO → Config → Verify.**