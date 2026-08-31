# Knowledge Base

Two tiers, different jobs — don't confuse them.

## `_static/` — compact, cross-cutting index

Five files, none of them narrative: `thresholds.yaml` (every severity number — memory, IO, index, waits, backup/CHECKDB/jobs, AG, query performance, storage), `taxonomy.md` (category → dashboard tab → script → tool name → source doc, one routing table shared by the `sql-server-dba` agent, `mcp/`'s tools, and `dashboard/backend/app/diagnostics.py`), `naming-conventions.md` (the SQL naming standard, mirrored from `CLAUDE.md`), `methodology.md` (a 10-step index pointing into `.claude/resources/performance/README.md`), and `scripts-index.md` (read-only/write status and MCP-wrapping per script).

This tier exists so a number or a rule only has **one** place to change. Nothing in here is prose you'd hand a new DBA to read top to bottom — it's what an agent (or a slash command) reads at the moment it needs a specific threshold or routing decision, instead of carrying its own copy that can silently drift.

## `<database-name>.md` — deep per-instance data

Built by `/sql-kb <database>`: table volumes (SMALL/MEDIUM/HIGH/CRITICAL classification), existing index inventory with usage stats, missing-index hints from the DMVs, unused-index candidates, and the SQL Server version/edition capabilities that gate certain DDL (`ONLINE = ON`, `RESUMABLE`, IQP features). Consumed by `/sql-pr-review` to assess risk against real table sizes, not guesses.

Different axis from `_static/`: this is per-database and time-sensitive (row counts go stale), where `_static/` is cross-cutting and changes only when the toolkit's own rules change. None of these files exist yet in this repo — `/sql-kb` hasn't been run against a real database here.

## Where the narrative lives

Neither tier explains *why* a threshold is what it is, or walks through *how* to actually run a tuning pass — that's `.claude/resources/performance/README.md` (10-step methodology, full walkthrough), `.claude/resources/maintenance/README.md` (Ola Hallengren setup, scheduling, use cases), and `.claude/resources/sql-scripts/README.md` (the 18-topic script library), written for a human reading them, same depth and detail as before — they moved under `.claude/resources/` alongside the rest of this toolkit's Claude Code tooling, they didn't get thinner. `_static/` cites those files as its source; it doesn't replace them. If you're onboarding a new DBA to this toolkit, start there — come back here only when you need the compact, machine-checkable version of the same rules.
