# Data Eyes — SQL Naming Standards

Canonical copy — mirrored from `CLAUDE.md` so agents and MCP-tool-generated DDL (e.g. `missing_indexes`'s generated `CREATE INDEX` text) can be checked against it without reading the whole project file. If these ever diverge, `CLAUDE.md` is legacy and this file wins; fix `CLAUDE.md` to match.

| Object | Convention | Example |
|---|---|---|
| Tables | singular snake_case | `customer`, `order_item` |
| Columns | snake_case | `first_name`, `email_address` |
| Primary keys | `[entity]_id` (never bare `id`) | `customer_id` |
| Foreign keys | `fk_[table]_[referenced_table]` | `fk_order_customer` |
| Procedures | `usp_[verb]_[entity]` (never `sp_` prefix) | `usp_get_customer` |
| Views | `vw_[entity]_[purpose]` | `vw_customer_summary` |
| Indexes (unique) | `ix_[table]_[col]` | `ix_customer_email` |
| Indexes (non-unique) | `nix_[table]_[col]` | `nix_order_customer_id` |
| Keywords | UPPERCASE, one clause per line, 4-space indent | — |

**Why `usp_` not `sp_`:** procedures prefixed `sp_` are resolved against `master` first on every call, adding overhead and risking collision with system procedures — this is also enforced as an anti-pattern in `.claude/agents/sql-server-dba.md`.

Used by: `/sql-guidelines` command (review target), `sql-server-dba` agent (DDL generation), `missing_indexes` MCP tool (generated index names should follow `ix_`/`nix_` conventions where practical — the DMV-driven auto-generated name in the script is a starting point, not gospel).
