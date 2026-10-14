# Database Statistics Analysis Scripts

## Overview
These SQL Server scripts analyze and update database statistics, which are crucial for the query optimizer to generate efficient execution plans. Statistics help SQL Server understand data distribution and selectivity in tables and indexes.

## Script 1: Statistics Modification Analysis

### Purpose
Examines all statistics in the database to identify when they were last updated and how many modifications have occurred since then.

```sql
SELECT DISTINCT
    OBJECT_NAME(s.[object_id]) AS TableName,
    c.name AS ColumnName,
    s.name AS StatName,
    STATS_DATE(s.[object_id], s.stats_id) AS LastUpdated,
    DATEDIFF(day, STATS_DATE(s.[object_id], s.stats_id), GETDATE()) AS DaysOld,
    dsp.modification_counter,
    s.auto_created,
    s.user_created,
    s.no_recompute,
    s.[object_id],
    s.stats_id,
    sc.stats_column_id,
    sc.column_id
FROM sys.stats s
JOIN sys.stats_columns sc
    ON sc.[object_id] = s.[object_id] 
    AND sc.stats_id = s.stats_id
JOIN sys.columns c 
    ON c.[object_id] = sc.[object_id] 
    AND c.column_id = sc.column_id
JOIN sys.partitions par 
    ON par.[object_id] = s.[object_id]
JOIN sys.objects obj 
    ON par.[object_id] = obj.[object_id]
CROSS APPLY sys.dm_db_stats_properties(sc.[object_id], s.stats_id) AS dsp
WHERE OBJECTPROPERTY(s.OBJECT_ID, 'IsUserTable') = 1
    AND (s.auto_created = 1 OR s.user_created = 1)
ORDER BY DaysOld DESC;
```

### Output Columns Analysis
| Column Name | Description |
|-------------|-------------|
| `TableName` | Name of the table |
| `ColumnName` | Column the statistics are based on |
| `StatName` | Name of the statistics object |
| `LastUpdated` | Date when statistics were last updated |
| `DaysOld` | Number of days since last update |
| `modification_counter` | Number of modifications since last update |
| `auto_created` | 1 if statistics were auto-created by SQL Server |
| `user_created` | 1 if statistics were manually created |
| `no_recompute` | 1 if statistics have automatic updates disabled |

### Key Information Provided
1. **Statistics Age**: How long since statistics were last updated (`DaysOld`)
2. **Modification Count**: How many changes occurred since last update
3. **Statistics Type**: Auto-created vs user-created statistics
4. **Update Settings**: Whether automatic recomputation is disabled

## Script 2: Statistics Update Command
```sql
-- Script 2: Update Statistics for Database
-- Purpose: Update all statistics in the current database
EXEC sp_updatestats;
GO
```

### What `sp_updatestats` Does
- Updates all statistics in the current database
- Only updates statistics that require updating (based on modification counters)
- Uses the `RESAMPLE` option to maintain existing sample rates
- More efficient than `UPDATE STATISTICS` on all objects individually

## When to Update Statistics
### Automatic Statistics Update (Recommended)
SQL Server automatically updates statistics when:
- Table is empty and data is added
- Number of row modifications exceeds a threshold:
  - When table has ≤ 500 rows: After 500 modifications
  - When table has > 500 rows: After 500 + (20% of row count) modifications

### Manual Statistics Update Needed When:
1. **Large Data Changes**: Bulk inserts, large updates, or deletions
2. **Query Performance Degradation**: Sudden slow queries
3. **After Index Rebuilds**: Statistics are updated during rebuilds, but verify
4. **Before Performance Testing**: Ensure accurate query plans
5. **Scheduled Maintenance**: Regular statistics maintenance windows

## Best Practices
### Monitoring Thresholds
```sql
-- Check for statistics that may need updating
-- Generally consider updating when:
-- 1. DaysOld > 30 AND modification_counter > 0
-- 2. modification_counter > 1000 + (0.20 * table_row_count)
```

### Update Strategies
```sql
-- Update specific statistics
UPDATE STATISTICS TableName StatName;

-- Update all statistics on a table with full scan
UPDATE STATISTICS TableName WITH FULLSCAN;

-- Update with specific sample rate
UPDATE STATISTICS TableName WITH SAMPLE 50 PERCENT;
```

### Critical Notes
1. **Auto-Update Impact**: Automatic statistics updates can cause brief query blocking
2. **Large Tables**: Consider using `WITH SAMPLE` or `WITH RESAMPLE` for large tables
3. **Maintenance Windows**: Schedule statistics updates during low activity periods
4. **Test First**: Always test statistics updates in non-production environments

## Usage Recommendation
Run **Script 1** regularly to monitor statistics health, and use **Script 2** during maintenance windows or when query performance issues are suspected. For critical databases, implement a monitoring strategy that alerts when statistics become significantly outdated.