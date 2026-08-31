# Unused Index Analysis Script

## Overview
This SQL Server query identifies the top 25 potentially unused nonclustered indexes in the current database by analyzing index usage statistics. It helps database administrators clean up indexes that consume storage and maintenance resources without providing query performance benefits.

## Purpose
Identify rarely-used indexes that may be candidates for removal

## Query Documentation

```sql
SELECT TOP 25
    o.name AS ObjectName,
    i.name AS IndexName,
    i.index_id AS IndexID,
    dm_ius.user_seeks AS UserSeek,
    dm_ius.user_scans AS UserScans,
    dm_ius.user_lookups AS UserLookups,
    dm_ius.user_updates AS UserUpdates,
    p.TableRows,
    -- Generate DROP INDEX statement
    'DROP INDEX ' + QUOTENAME(i.name) 
    + ' ON ' + QUOTENAME(s.name) + '.' 
    + QUOTENAME(OBJECT_NAME(dm_ius.OBJECT_ID)) AS 'drop statement'

FROM sys.dm_db_index_usage_stats dm_ius
INNER JOIN sys.indexes i 
    ON i.index_id = dm_ius.index_id 
    AND dm_ius.OBJECT_ID = i.OBJECT_ID
INNER JOIN sys.objects o 
    ON dm_ius.OBJECT_ID = o.OBJECT_ID
INNER JOIN sys.schemas s 
    ON o.schema_id = s.schema_id
INNER JOIN (
    -- Calculate table row counts per index
    SELECT 
        SUM(p.rows) AS TableRows, 
        p.index_id, 
        p.OBJECT_ID
    FROM sys.partitions p 
    GROUP BY p.index_id, p.OBJECT_ID
) p ON p.index_id = dm_ius.index_id 
    AND dm_ius.OBJECT_ID = p.OBJECT_ID

-- Filter conditions
WHERE OBJECTPROPERTY(dm_ius.OBJECT_ID, 'IsUserTable') = 1  -- Only user tables
    AND dm_ius.database_id = DB_ID()                      -- Current database only
    AND i.type_desc = 'nonclustered'                      -- Nonclustered indexes only
    AND i.is_primary_key = 0                              -- Exclude primary keys
    AND i.is_unique_constraint = 0                        -- Exclude unique constraints

-- Order by total reads (ascending = least used first)
ORDER BY (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) ASC
GO
```

## Output Columns
| Column Name | Description |
|-------------|-------------|
| `ObjectName` | Name of the table containing the index |
| `IndexName` | Name of the index |
| `IndexID` | Internal ID of the index |
| `UserSeek` | Number of index seek operations |
| `UserScans` | Number of index scan operations |
| `UserLookups` | Number of bookmark lookups |
| `UserUpdates` | Number of update operations (maintenance cost) |
| `TableRows` | Approximate number of rows in the table |
| `drop statement` | Ready-to-use DROP INDEX statement |

## Key Features
1. **Usage Analysis**: Examines seek, scan, and lookup operations to determine index utilization
2. **Focused Scope**: Analyzes only:
   - User tables (no system tables)
   - Current database
   - Nonclustered indexes
   - Excludes primary keys and unique constraints
3. **Maintenance Cost Awareness**: Shows update counts to highlight index maintenance overhead
4. **Size Context**: Includes row counts to understand table size impact
5. **Actionable Output**: Generates ready-to-use DROP statements

## Usage Statistics Explained
- **User Seeks**: Index seek operations (efficient lookups)
- **User Scans**: Index scan operations (less efficient)
- **User Lookups**: Bookmark lookups (key lookups)
- **User Updates**: Maintenance operations (insert/update/delete overhead)

## Important Considerations
⚠️ **Critical Warnings Before Index Removal:**
1. **Statistics Reset**: `sys.dm_db_index_usage_stats` resets when SQL Server restarts
2. **Recent Usage**: Check server uptime to ensure statistics represent meaningful time periods
3. **Seasonal Usage**: Some indexes may be used only during specific periods (month-end, etc.)
4. **Primary Keys**: Never remove primary key indexes
5. **Unique Constraints**: Never remove unique constraint indexes
6. **Testing**: Always test in non-production environments first
7. **Backup**: Have a backup plan to recreate indexes if needed

## Recommended Analysis Steps
1. **Check Server Uptime**: 
```sql
SELECT sqlserver_start_time FROM sys.dm_os_sys_info
```
2. **Verify Usage Patterns**: Look for indexes with zero or very low read operations
3. **Consider Maintenance Cost**: High UserUpdates with low reads indicate costly unused indexes
4. **Check for Dependencies**: Ensure no processes rely on these indexes
5. **Monitor After Removal**: Watch for performance degradation

This script helps optimize database performance by identifying indexes that consume resources without providing query performance benefits.