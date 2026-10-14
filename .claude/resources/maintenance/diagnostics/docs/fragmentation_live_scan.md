# Index Fragmentation — Live Scan

**Script:** `fragmentation_live_scan.sql` · **MCP tool:** `index_fragmentation(database=None, min_frag_pct=5, top_n=50)`

## Purpose

Live `sys.dm_db_index_physical_stats` scan (actual current fragmentation), distinct from `.claude/resources/performance/additional_queries/unused_indexes.sql` (usage-stats based). Feeds the Index & Buffer tab and Step 2 of the performance methodology.

## Output columns

`DatabaseName`, `TableName`, `IndexName`, `IndexType`, `FragmentationPct`, `PageCount`, `RecommendedAction` (`NONE`/`REORGANIZE`/`REBUILD`), `severity`.

## Severity logic

`< 5%` → `OK`; `5–30%` → `WARNING` (`REORGANIZE`); `> 30%` → `CRITICAL` (`REBUILD`). Matches the fragmentation bands already documented in `.claude/resources/performance/README.md` Step 2 and the workbook's Index_Maintenance tab.

## Notes

- Uses `'LIMITED'` scan mode for lower overhead, but this is still not a cheap query on large databases — don't poll it on a short interval.
- Filters out indexes with `page_count <= 1000` (trivially small, rebuild/reorganize churn not worth it).
- `sys.dm_db_index_physical_stats` requires a specific database context; `@DatabaseName = NULL` defaults to the current connection's database.
