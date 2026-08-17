# Data Eyes — Scripts Index

Catalog of every script in the toolkit, its read-only/write nature, and whether an MCP tool wraps it. This is the layer that lets an agent (or the dashboard backend) answer "what can I run to check X" without re-deriving it from folder names each time.

## performance/additional_queries/ — read-only, diagnostic

| Script | Read-only copy | Structured (`.json.sql`) copy | MCP tool |
|---|---|---|---|
| Missing indexes | `missing_indexes.sql` | `missing_indexes.json.sql` | `missing_indexes` |
| Unused indexes | `unused_indexes.sql` | `unused_indexes.json.sql` | `unused_indexes` |
| Wait statistics | `wait_statistics.sql` | `wait_statistics.json.sql` | `wait_stats` |
| Stale statistics | `update_statistics.sql` | `update_statistics.json.sql` | `stale_statistics` |
| Top queries by duration | — (structured form only, see below) | `top_queries.json.sql` | `top_queries` |

The first four `.json.sql` copies emit `severity` (from [[thresholds]]) and `FOR JSON AUTO` output alongside an unchanged plain `.sql` original (copy-paste/SSMS form). `top_queries.json.sql` was authored directly in structured form during Phase 3 — it closed a gap where this logic previously existed only as inline Grafana panel SQL, so there was no pre-existing plain `.sql` to keep a sibling of.

## maintenance/ — mixed

| Script | Type | MCP tool |
|---|---|---|
| `playbook.sql` | Write (backup/CHECKDB/index EXECUTE calls) | none — action script, human-confirmed only |
| `sql_agent_schedule_playbook.sql` | Write (creates SQL Agent jobs) | none — action script, human-confirmed only |
| `use_cases/backup_ola_hallengren.sql` (15 scenarios) | Write, reference | none |
| `use_cases/dbcc_check_ola_hallengren.sql` (10 scenarios) | Write, reference | none |
| `use_cases/index_statistics_ola_hallengren.sql` (10 scenarios) | Write, reference | none |
| `diagnostics/backup_health_check.sql` | Read-only, live observation | `backup_health` |
| `diagnostics/checkdb_staleness.sql` | Read-only, live observation | `checkdb_health` |
| `diagnostics/fragmentation_live_scan.sql` | Read-only, live observation | `index_fragmentation` |
| `diagnostics/blocking_chain_snapshot.sql` | Read-only, live observation | `blocking_snapshot` |
| `diagnostics/ag_sync_health.sql` | Read-only, live observation | `ag_health` |
| `diagnostics/job_failure_scan.sql` | Read-only, live observation | `job_health` |
| `diagnostics/db_space_check.sql` | Read-only, live observation | `db_space` |

The `diagnostics/` folder is what closes the gap identified in the rearchitecture plan: before this pass, `maintenance/` had zero live "is it healthy right now" queries — only action scripts.

## sql-scripts/ — 18 topic folders, ~84 scripts, unmodified

Not individually cataloged here (would duplicate `/sql-scripts` command's routing table and drift immediately). Folders: `audit`, `backup_recovery`, `custom_alert_emails`, `database_size`, `free_space`, `functions`, `helps`, `index`, `lock`, `query_store`, `server`, `sql_access`, `sql_agent`, `sql_docker` (currently empty), `sql_profiler`, `ssis`, `ssrs`, `triggers`. None of these are MCP-tool-wrapped — they remain copy-paste/human-routed via `/sql-scripts`. If a script here proves to be a recurring live-diagnostic need, promote it into `maintenance/diagnostics/` or `performance/additional_queries/` with a matching MCP tool rather than wrapping it in place.

## mcp/ generic tools (pre-existing, not diagnostic-specific)

`execute_sql`, `list_schemas`, `list_tables`, `schema_discovery`, `describe_table`, `get_database_info`, `get_policy_info`, `check_db_connection`, `get_relationships`, `sample_table`, `distinct_values`, `list_databases` — schema/data exploration, not wrapping any script in this repo. See `mcp/README.md`.
