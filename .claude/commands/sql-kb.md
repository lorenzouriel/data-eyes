---
name: sql-kb
description: SQL Server knowledge base builder — collects table volumes and index strategies for a target database via catalog queries
---

# /sql-kb Command

> Build or refresh the knowledge base for a database. Run this once before using `/sql-pr-review`, or whenever the KB is stale.

## Usage

```
/sql-kb <database-name>             — build KB for a database (first time)
/sql-kb --refresh <database-name>   — overwrite existing KB with fresh data
```

## Examples

```
/sql-kb <your-database>
/sql-kb AdventureWorks
/sql-kb --refresh <your-database>
```

---

## What This Skill Does

1. Presents four catalog queries (KB-0 through KB-4) as copy-paste blocks for the user to run in SSMS, Azure Data Studio, or sqlcmd
2. Collects results pasted back by the user
3. Classifies each table by volume (SMALL / MEDIUM / HIGH / CRITICAL)
4. Writes the knowledge base to `.claude/knowledge-base/<database-name>.md`

**Never executes queries automatically — the user runs them and pastes results back.**

---

## Process

### Step 1: Confirm Database and Schema

Ask the user (if not already specified):
- **Database name** — which database the queries should target
- **Schema** — if not `dbo`

Check whether `.claude/knowledge-base/<database-name>.md` already exists.
- **File exists and no `--refresh` flag** → warn: "KB already exists for `<database-name>` (generated: `<date>`). Use `--refresh` to overwrite."
- **File missing or `--refresh`** → proceed to Step 2.

---

### Step 2: Run Catalog Queries

Present each query below as a copy-paste block. Ask: "Ready to paste and run these queries? (yes/no)"

After the user confirms, show each query one at a time with its `sqlcmd` equivalent. Wait for the user to paste results before showing the next.

---

#### Query KB-0: SQL Server Version and Edition

Run this first. The result determines which features are safe to recommend in `/sql-pr-review`.

```sql
SELECT
    @@VERSION                               AS sql_version,
    SERVERPROPERTY('Edition')               AS edition,
    SERVERPROPERTY('ProductVersion')        AS product_version,
    SERVERPROPERTY('ProductMajorVersion')   AS major_version,
    SERVERPROPERTY('EngineEdition')         AS engine_edition;
-- EngineEdition: 2 = Standard, 3 = Enterprise/Developer, 5 = Azure SQL
-- major_version: 16 = SQL Server 2022, 15 = 2019, 14 = 2017, 13 = 2016
```

Store the result in the KB header. Apply these rules in `/sql-pr-review`:
- `EngineEdition = 2` (Standard Edition) → **never** recommend `ONLINE = ON` for index operations
- `major_version < 14` (pre-SQL Server 2017) → offer `STUFF + FOR XML PATH` fallback instead of `STRING_AGG`
- `major_version >= 16` (SQL Server 2022) → IQP features (PSP Optimization, CE Feedback, DOP Feedback) are available

---

#### Query KB-1: Table Row Counts and Size

```sql
USE [<DatabaseName>];

SELECT
    s.name                                  AS schema_name,
    t.name                                  AS table_name,
    p.rows                                  AS row_count,
    SUM(a.total_pages) * 8 / 1024.0        AS total_size_mb,
    SUM(a.used_pages) * 8 / 1024.0         AS used_size_mb,
    t.create_date,
    t.modify_date
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
JOIN sys.allocation_units a ON p.partition_id = a.container_id
GROUP BY s.name, t.name, p.rows, t.create_date, t.modify_date
ORDER BY p.rows DESC;
```

---

#### Query KB-2: Existing Indexes Per Table

```sql
USE [<DatabaseName>];

SELECT
    s.name                              AS schema_name,
    t.name                              AS table_name,
    i.name                              AS index_name,
    i.type_desc                         AS index_type,
    i.is_unique,
    i.is_primary_key,
    STRING_AGG(
        CASE WHEN ic.is_included_column = 0 THEN c.name END, ', '
    ) WITHIN GROUP (ORDER BY ic.index_column_id) AS key_columns,
    STRING_AGG(
        CASE WHEN ic.is_included_column = 1 THEN c.name END, ', '
    ) WITHIN GROUP (ORDER BY ic.index_column_id) AS included_columns,
    ius.user_seeks,
    ius.user_scans,
    ius.user_updates,
    ius.last_user_seek,
    ius.last_user_scan
FROM sys.indexes AS i
INNER JOIN sys.tables AS t ON i.object_id = t.object_id
INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
INNER JOIN sys.index_columns AS ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns AS c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
LEFT JOIN sys.dm_db_index_usage_stats AS ius
    ON i.object_id = ius.object_id AND i.index_id = ius.index_id AND ius.database_id = DB_ID()
INNER JOIN (
    SELECT object_id
    FROM sys.partitions
    WHERE index_id IN (0, 1)
    GROUP BY object_id
    HAVING SUM(rows) >= 10000000
) AS big ON t.object_id = big.object_id
WHERE i.type > 0
GROUP BY
    s.name, t.name, i.name, i.type_desc, i.is_unique, i.is_primary_key,
    ius.user_seeks, ius.user_scans, ius.user_updates, ius.last_user_seek, ius.last_user_scan
ORDER BY s.name, t.name, i.name;
```

---

#### Query KB-3: SQL Server Missing Index Hints

```sql
USE [<DatabaseName>];

SELECT
    OBJECT_SCHEMA_NAME(mid.object_id)           AS schema_name,
    OBJECT_NAME(mid.object_id)                  AS table_name,
    migs.avg_total_user_cost * migs.avg_user_impact
        * (migs.user_seeks + migs.user_scans)   AS improvement_measure,
    'CREATE INDEX [nix_' + OBJECT_NAME(mid.object_id)
        + '_missing_' + CAST(mid.index_handle AS VARCHAR) + '] ON '
        + mid.statement + ' ('
        + ISNULL(mid.equality_columns, '')
        + CASE WHEN mid.inequality_columns IS NOT NULL
               AND mid.equality_columns IS NOT NULL THEN ', ' ELSE '' END
        + ISNULL(mid.inequality_columns, '') + ')'
        + ISNULL(' INCLUDE (' + mid.included_columns + ')', '')
        AS suggested_index,
    mid.equality_columns,
    mid.inequality_columns,
    mid.included_columns,
    migs.user_seeks,
    migs.user_scans
FROM sys.dm_db_missing_index_details mid
JOIN sys.dm_db_missing_index_groups mig ON mid.index_handle = mig.index_handle
JOIN sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
WHERE mid.database_id = DB_ID()
ORDER BY improvement_measure DESC;
```

---

#### Query KB-4: Unused and Redundant Indexes

```sql
USE [<DatabaseName>];

SELECT
    s.name                          AS schema_name,
    t.name                          AS table_name,
    i.name                          AS index_name,
    i.type_desc,
    ius.user_seeks,
    ius.user_scans,
    ius.user_lookups,
    ius.user_updates,
    'DROP INDEX [' + i.name + '] ON [' + s.name + '].[' + t.name + '];'
        AS drop_statement
FROM sys.indexes i
JOIN sys.tables t ON i.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema_id
LEFT JOIN sys.dm_db_index_usage_stats ius
    ON i.object_id = ius.object_id
    AND i.index_id = ius.index_id
    AND ius.database_id = DB_ID()
WHERE i.is_primary_key = 0
  AND i.is_unique_constraint = 0
  AND i.type > 0
  AND (ius.user_seeks IS NULL OR ius.user_seeks = 0)
  AND (ius.user_scans IS NULL OR ius.user_scans = 0)
  AND (ius.user_lookups IS NULL OR ius.user_lookups = 0)
```

---

### Step 3: Classify Tables by Volume

After collecting KB-1 results:

| Row Count | Classification | Label |
|-----------|---------------|-------|
| 0 – 99,999 | Small | `SMALL` |
| 100,000 – 9,999,999 | Medium | `MEDIUM` |
| 10,000,000 – 99,999,999 | High Volume | `HIGH` |
| 100,000,000+ | Critical Volume | `CRITICAL` |

#### Index Strategy by Volume

| Classification | Recommended Strategy |
|---------------|---------------------|
| `SMALL` | PK clustered index is sufficient; additional indexes only if explicitly queried |
| `MEDIUM` | Covering indexes on frequent `WHERE`/`JOIN` columns; avoid over-indexing (each index costs on writes) |
| `HIGH` | Clustered index on PK or natural key; narrow NC indexes on selective filter columns; INCLUDE columns to avoid key lookups; consider filtered indexes for partial scans; avoid wide composite keys |
| `CRITICAL` | Everything for `HIGH` plus: columnstore indexes for analytics/aggregations; partition pruning if time-series; avoid heap; batch writes; review index fill factor |

---

### Step 4: Write the Knowledge Base File

Write to `.claude/knowledge-base/<database-name>.md` using the format below. If the directory does not exist, inform the user to create it.

```markdown
# Knowledge Base: <DatabaseName>

> Generated: <date>
> Server: <server>
> EngineEdition: <N> (<label> — ONLINE = ON supported/not supported)
> MajorVersion: <N> — STRING_AGG available/not available; IQP features available/not available
> Refreshed by: /sql-kb --refresh

---

## Volume Summary

| Schema | Table | Rows | Size (MB) | Classification |
|--------|-------|------|-----------|---------------|
| dbo | order | 15,432,100 | 2,841.3 | HIGH |
| dbo | customer | 980,200 | 312.1 | MEDIUM |
| dbo | product | 4,500 | 1.8 | SMALL |

---

## Table Details

### `<schema>.<table>` — <CLASSIFICATION> (<row_count> rows, <size_mb> MB)

**Recommended Index Strategy:** <one-line from the strategy table above>

#### Existing Indexes

| Index Name | Type | Key Columns | Included Columns | Seeks | Scans | Updates |
|------------|------|-------------|-----------------|-------|-------|---------|

#### Missing Index Hints (from DMV)

| Improvement Score | Suggested Index | Seeks | Scans |
|------------------|----------------|-------|-------|

#### Unused Indexes (candidates for removal)

| Index Name | Type | Updates (write cost) | Drop Statement |
|------------|------|---------------------|----------------|

---

## Index Health Summary

- **Total indexes:** <N>
- **Missing index hints:** <N>
- **Unused indexes:** <N> (review before dropping — DMV resets on restart)
```

---

## Output Rules

- Present each query as a copy-paste block — **never execute automatically**
- Show the equivalent `sqlcmd` command alongside each query for reference:
  ```
  sqlcmd -S <server> -U <user> -P <pass> -d <database> -Q "<query>"
  ```
- If `$MSSQL_CONNECTION` is set in the environment, reference it by name only — never read or display its value
- Never store passwords or connection strings in the KB file
- Confirm before overwriting an existing KB file: "Overwrite `.claude/knowledge-base/<database-name>.md`? (yes/no)"
- Missing index DMV data resets when SQL Server restarts — note this caveat in the KB file
- `DROP INDEX` candidates require explicit user confirmation — never present removal as a safe default

---

## When to Refresh

Recommend refreshing when:
- More than 30 days have passed since last generation date
- A major data load or migration was completed
- `/sql-pr-review` references a table not found in the KB
