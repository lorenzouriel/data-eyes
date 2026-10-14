---
name: sql-pr-review
description: SQL Server PR reviewer — validates SQL changes against clean code guidelines and a knowledge base of table volumes and index strategies
---

# /sql-pr-review Command

> Review SQL changes from a PR with full awareness of table volumes and index strategies — flags risky operations, missing indexes, and guideline violations.
> Requires a knowledge base built by `/sql-kb <database>`.

## Usage

```
/sql-pr-review <paste SQL changes or describe the PR>
/sql-pr-review --summary <SQL>             — one-paragraph verdict with blocking issues only (default)
/sql-pr-review --full <SQL>                — full review with all sections and corrected SQL
/sql-pr-review --json <SQL>                — machine-readable JSON output for CI automation
/sql-pr-review --gh-comment <SQL>          — GitHub PR comment format (blocking / non-blocking findings)
/sql-pr-review --branch-diff <branch>      — review SQL files changed between current branch and <branch>, output as GitHub PR comment
```

## Examples

```
/sql-pr-review "ALTER TABLE sales_order ADD COLUMN payment_method VARCHAR(50)"
/sql-pr-review "CREATE INDEX idx_sales_order_date ON sales_order(created_at)"
/sql-pr-review "SELECT * FROM customer JOIN sales_order ON customer.id = sales_order.customer_id WHERE sales_order.status = 'pending'"
/sql-pr-review "CREATE PROCEDURE usp_get_orders AS BEGIN SELECT order_id, total FROM sales_order WHERE status = 'active' END"
/sql-pr-review --summary "ALTER TABLE session ADD COLUMN recording_type TINYINT NOT NULL DEFAULT 0"
/sql-pr-review --gh-comment "CREATE INDEX nix_delivery_status ON delivery(status) INCLUDE (created_at)"
/sql-pr-review --branch-diff feature/add-indexes
/sql-pr-review --branch-diff origin/feature/add-indexes
```

---

## What This Skill Does

1. Loads the knowledge base for the target database
2. Parses every table referenced in the submitted SQL
3. Looks up each table in the knowledge base to assess volume and existing index coverage
4. Flags risk level (LOW / MEDIUM / HIGH / CRITICAL) based on table size and operation type — with categorical blockers that override the score
5. Applies all Data Eyes naming, formatting, performance, and security guidelines
6. Outputs a structured review: risk flags, index recommendations, guideline violations, and corrected SQL

---

## Process

### Step 1: Identify the Database and Load Knowledge Base

Ask the user (if not already specified):
- **Database name** — which database the SQL targets
- **Schema** — if not `dbo`

Then check whether the knowledge base exists:

```
.claude/knowledge-base/<database-name>.md
```

- **File exists** → load it and proceed to Step 2
- **File missing** → halt and tell the user:

  > "No knowledge base found for `<database-name>`. Run `/sql-kb <database-name>` to build it, then retry."

The KB header must contain three environment facts that several rules depend on:

| KB header field | Rules that depend on it |
|---|---|
| **SQL Server version** | `ONLINE = ON` availability, `STRING_AGG` vs `STUFF` fallback, scalar UDF inlining (2019+), `RESUMABLE` index ops |
| **Edition** (Enterprise / Standard / Azure SQL) | `ONLINE = ON` (Enterprise/Azure only), metadata-only `ADD COLUMN NOT NULL DEFAULT` (Enterprise/Azure only) |
| **Database compatibility level** | IQP features — PSP Optimization, CE Feedback, and DOP Feedback all require compat level **160**, not just Query Store |

If any of the three is missing from the KB header, mark all dependent recommendations as **conditional** and tell the user to refresh the KB.

If the KB generation date is older than 30 days, add a warning at the top of the review output:
> "Knowledge base is N days old — row counts may be stale. Run `/sql-kb --refresh <database-name>` to update."

---

### Step 1b: Branch Diff Mode (`--branch-diff <branch>`)

When invoked with `--branch-diff`, skip manual SQL input. Instead:

1. Identify which `.sql` files changed between the current branch and the target:

```bash
git diff --name-status <branch>...HEAD -- "*.sql"
```

2. For each **added or modified** `.sql` file, retrieve the **full file content at HEAD** — never review orphaned diff fragments, because an added predicate inside an existing 200-line procedure loses all statement context and the SARG/JOIN checks will misfire:

```bash
git show HEAD:<file-path>
```

3. Also capture the line-level diff for annotation:

```bash
git diff <branch>...HEAD -- <file-path>
```

   Review the **full file**, but annotate each finding with whether it sits on a **changed line** (from the diff) or on **pre-existing code**. Findings on changed lines are in scope for the PR verdict; findings on pre-existing code are reported as `[NOTE — pre-existing]` and never block.

4. For **deleted lines**, do not review them — but flag any removed `DROP INDEX`, `DROP TABLE`, `CREATE INDEX`, or constraint definitions, since a deletion can itself be a risk (e.g. an index removed from a migration script).

5. Identify the database from one of:
   - A `USE [<database>]` statement in the file
   - The user's explicit argument: `/sql-pr-review --branch-diff <branch> <database>`
   - Ask the user if neither is found

6. Load the KB as normal (Step 1), then run Steps 2–5 per file.

7. Output defaults to `--gh-comment` format — one comment block per changed file, aggregated under a single review header.

> **If no `.sql` files appear in the diff**, tell the user: "No SQL files found in diff between current branch and `<branch>`. Nothing to review."

---

### Step 2: Parse the SQL Changes

Identify all objects referenced in the submitted SQL:

| Pattern to detect | Extract |
|---|---|
| `FROM <table>`, `JOIN <table>` | Table name used in reads |
| `INSERT INTO <table>` | Table name used in writes |
| `UPDATE <table>` | Table name used in writes |
| `DELETE FROM <table>` | Table name used in writes |
| `MERGE <table>` | Table used as merge target |
| `ALTER TABLE <table>` | Table being modified |
| `CREATE INDEX ... ON <table>` | Table receiving a new index |
| `DROP INDEX ... ON <table>` | Table losing an index |
| `CREATE TABLE <table>` | New table (no KB entry yet — flag as "new, no volume data") |

For each table extracted, look it up in the loaded knowledge base.

> **Parsing caveat:** This is best-effort text matching, not a full SQL parser. It will miss: aliased table references (`FROM sales_order AS so`), quoted identifiers (`[session]`), tables defined in a `WITH` CTE block, `#temp` tables, dynamic SQL strings, synonyms, and cross-database or cross-schema objects not in the current KB. For complex SQL with any of these patterns, flag the review as **requires manual verification** before the risk assessment.

---

### Step 3: Assess Risk per Table

#### Categorical Blockers (override the score — always CRITICAL)

Some findings are blocking regardless of any numeric score. If any of these appear, the PR verdict is `CRITICAL` and the finding is reported as `BLOCKING`:

| Categorical blocker | Why |
|---|---|
| `UPDATE` or `DELETE` with **no `WHERE` clause** on any table | Rewrites/removes every row; almost never intentional in a PR |
| `ALTER TABLE … ADD COLUMN … NOT NULL` **without a default** on a table with rows | **Execution error** — the statement fails outright on any populated table. Report as "will not execute", not as a lock risk |
| `DROP INDEX` on a table with active seeks (per KB) | Removes a plan the workload depends on |
| `TRUNCATE TABLE` on `HIGH`/`CRITICAL` table (SEC-7) | Destructive, minimally logged, no per-row recovery |
| `DROP TABLE` / `DROP DATABASE` in a migration (SEC-8) | Destructive |

#### Risk Scoring

For each table touched by the SQL:

| Condition | Risk added |
|---|---|
| Table is `HIGH` or `CRITICAL` volume | +2 |
| Operation is `UPDATE`, `DELETE`, or `INSERT` on `HIGH`/`CRITICAL` | +2 |
| `ALTER TABLE … ADD COLUMN NOT NULL DEFAULT …` on `HIGH`/`CRITICAL` — **Enterprise/Azure SQL** (metadata-only runtime default) | +1 |
| `ALTER TABLE … ADD COLUMN NOT NULL DEFAULT …` on `HIGH`/`CRITICAL` — **Standard Edition or pre-2012** (size-of-data operation: every row is touched) | +4 |
| `ALTER TABLE … ADD COLUMN` nullable on `HIGH`/`CRITICAL` (metadata-only) | +1 |
| `ALTER TABLE … ALTER COLUMN` (type change) on any table with data | +3 |
| `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY … WITH CHECK` on `HIGH`/`CRITICAL` | +3 |
| `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY … WITH NOCHECK` | +1 — but always add the note: *constraint is created untrusted (`is_not_trusted = 1`); the optimizer cannot use it for join elimination. Schedule `ALTER TABLE … WITH CHECK CHECK CONSTRAINT …` off-hours to validate and trust it* |
| `ALTER TABLE … DROP COLUMN` on `HIGH`/`CRITICAL` | +2 |
| `CREATE INDEX` or `ALTER INDEX … REBUILD` without `ONLINE = ON` on `MEDIUM`+ | +2 |
| `SELECT` with no `WHERE` clause on `HIGH`/`CRITICAL` | +2 |
| Query filters on a non-indexed column of a `HIGH`/`CRITICAL` table | +2 |
| Explicit `BEGIN TRAN` spanning multiple large DML statements, or DML inside a transaction with no visible `COMMIT` in the same script | +2 |
| `MERGE` statement on any table | +2 (see GEN-10) |
| Scalar UDF invoked anywhere in the query on `HIGH`/`CRITICAL` (pre-2019, or 2019+ with inlining exclusions) | +2 |
| Missing index hint exists for matching columns | +1 |
| Unused index being added (duplicate or redundant) | +1 |
| Cursor declared without `LOCAL FAST_FORWARD READ_ONLY` | +1 |

> **Note on transactions:** a single autocommitted DML statement (no explicit transaction) is the **safe default** in SQL Server — do not penalize it. The risk is the opposite pattern: long-held explicit transactions that pin locks across multiple statements.

**Total Risk Score:**

| Score | Level | Label |
|-------|-------|-------|
| 0 | Safe | `LOW` |
| 1–2 | Review recommended | `MEDIUM` |
| 3–5 | Requires careful review | `HIGH` |
| 6+ or any categorical blocker | Blocking — do not merge without DBA sign-off | `CRITICAL` |

---

### Step 4: Apply Data Eyes Naming and Formatting Guidelines

Run the same checks as `/sql-guidelines` on the submitted SQL. Read `.claude/knowledge-base/_static/naming-conventions.md` for the canonical table — don't rely on a memorized copy, it's the single source `/sql-guidelines`, the `sql-server-dba` agent, and the `missing_indexes` MCP tool all check against too:

1. **Naming Conventions** (per `naming-conventions.md`) — tables singular snake_case, columns snake_case, PK `[entity]_id`, FK column `[ref_entity]_id`, **FK constraint name `fk_[table]_[referenced_table]`** (a separate check from the column name — flag a correctly-named FK column with a missing or wrongly-shaped constraint name too), procedures `usp_[verb]_[entity]`, views `vw_[entity]_[purpose]`, indexes `ix_` (unique) / `nix_` (non-unique)
   - **Never use the `sp_` prefix** — SQL Server resolves `sp_`-prefixed names against `master` first (extra metadata lookup, potential collision with system procedures). Flag any `sp_` procedure as a naming violation with fix `usp_`.
   - **Reserved-word identifiers must be bracket-quoted.** Singular snake_case naming guarantees collisions with reserved words (`order`, `user`, `session`, `group`, `transaction`) — these must always be written as `[order]`, `[user]`, etc. Flag any unbracketed reserved word.
2. **Formatting** — keywords UPPERCASE, one clause per line, 4-space indent, explicit column lists, `AS` for aliases
3. **Avoid SELECT \*** — except inside `EXISTS`
4. **Comments** — must explain why, not what; header block required for procedures and views

For each violation found:

| Field | What to write |
|---|---|
| **Category** | Naming / Formatting / SELECT * / Comments |
| **Rule** | The specific rule broken |
| **Offending token** | Exact text from the submitted SQL |
| **Fix** | What it should be |

---

### Step 4b: Apply SQL Performance Best Practices

Check the submitted SQL against the categories below. For each violation found:

| Field | What to write |
|---|---|
| **Category** | SARGability / SELECT / JOIN / Aggregation / CTE & Temp / Plan Cache / General |
| **Rule ID** | e.g. `SARG-1` |
| **Anti-pattern** | Exact text from the submitted SQL |
| **Fix** | Corrected form |

#### SARGability — WHERE Clause

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `SARG-1` | Function on indexed column: `WHERE YEAR(created_at) = 2026` | `WHERE created_at >= '2026-01-01' AND created_at < '2027-01-01'` |
| `SARG-2` | Implicit type conversion on column side: `WHERE CAST(id AS VARCHAR) = '123'` | Match column type to literal type |
| `SARG-3` | ISNULL/COALESCE wrapping indexed column: `WHERE ISNULL(status, '') = 'Active'` | `WHERE status = 'Active'` — the NULL branch can never match `'Active'`, so the wrapper is dead weight. Only add `OR status IS NULL` when the fallback value equals the compared literal |
| `SARG-4` | Leading wildcard LIKE: `WHERE name LIKE '%value'` | Use Full-Text Search or rewrite with trailing wildcard if possible |
| `SARG-5` | Data type mismatch between column and predicate literal | Match types explicitly — mismatches force a scan on the column side |

#### SELECT

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `SEL-1` | `SELECT *` (covered by Step 4, flag here if inside a subquery too) | List columns explicitly |
| `SEL-2` | `SELECT DISTINCT` on large result set without verifying duplicates exist | Confirm duplicates; use `GROUP BY` if aggregating |
| `SEL-3` | Correlated subquery in SELECT list (N+1 pattern) | Rewrite as `JOIN` or `OUTER APPLY` |

#### JOIN

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `JOIN-1` | Implicit JOIN syntax: `FROM a, b WHERE a.id = b.id` | Use explicit `INNER JOIN … ON` syntax |
| `JOIN-2` | Data type mismatch in JOIN condition | Align types — mismatches eliminate index seeks on the coerced side |
| `JOIN-3` | Function or expression in JOIN predicate: `ON CAST(a.id AS INT) = b.id` | Materialize or fix data type at source |
| `JOIN-4` | Join hints (`LOOP`, `MERGE`, `HASH`) without documented justification | Remove; let the optimizer decide unless a DBA has proven the hint helps |

#### Aggregation

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `AGG-1` | DISTINCT and non-DISTINCT aggregates in the same SELECT | **Evaluate** splitting into two aggregations — flag as review item |
| `AGG-2` | `HAVING` used to filter non-aggregate columns: `HAVING status = 'active'` | Move predicate to `WHERE` |
| `AGG-3` | Aggregation on non-indexed column of HIGH/CRITICAL table without a covering index | Add index on GROUP BY/filter columns |

#### CTEs, Temp Tables, and Subqueries

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `CTE-1` | CTE referenced more than once in the same query (re-executed each reference) | Materialize to a `#temp` table when referenced 2+ times |
| `CTE-2` | Subquery nesting 3+ levels deep | Break into CTEs or temp tables |
| `CTE-3` | `@table` variable holding a large intermediate result set | Use a `#temp` table — table variables carry no statistics |

> **Do not flag `WHERE EXISTS (…)` correlated subqueries.** `EXISTS` compiles to a semi-join, which is typically as good as or better than an `INNER JOIN` rewrite.

#### Parameter Sniffing and Plan Cache

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `PLAN-1` | Stored procedure filters on high-skew column with no plan cache mitigation | Add `OPTION (OPTIMIZE FOR UNKNOWN)` or `OPTION (RECOMPILE)` |
| `PLAN-2` | Procedure accepts wide date ranges on HIGH/CRITICAL tables with a single cached plan | Evaluate `OPTION (RECOMPILE)` or SQL Server 2022 PSP Optimization |
| `PLAN-3` | Local variable assigned from parameter and used in predicate (defeats sniffing but loses optimization) | Document intent; prefer `OPTIMIZE FOR UNKNOWN` |

#### General

| Rule | Anti-pattern | Fix |
|------|-------------|-----|
| `GEN-1` | Stored procedure missing `SET NOCOUNT ON` | Add `SET NOCOUNT ON;` as first statement |
| `GEN-2` | `NOLOCK` / `WITH (NOLOCK)` without explicit justification | Flag for DBA review — dirty reads can return uncommitted or phantom rows |
| `GEN-3` | `TOP N` without `ORDER BY` | Non-deterministic result — add explicit `ORDER BY` |
| `GEN-4` | Unbounded query on HIGH/CRITICAL table | Add a filter or `TOP` |
| `GEN-5` | `SELECT INTO #temp` without explicit column definition for large transformations | Prefer `CREATE TABLE #temp (…); INSERT INTO #temp SELECT …` |
| `GEN-6` | Temp table string columns declared without `COLLATE database_default` | Add `COLLATE database_default` to text columns in `#temp` |
| `GEN-7` | Deprecated types `TEXT` / `NTEXT` / `IMAGE` on new columns | Use `VARCHAR(MAX)` / `NVARCHAR(MAX)` / `VARBINARY(MAX)` |
| `GEN-8` | `DATETIME` on new columns | Use `DATETIME2(n)` with explicit precision |
| `GEN-9` | `NEWID()` as default on a clustered primary key | Use `NEWSEQUENTIALID()` or `IDENTITY` |
| `GEN-10` | `MERGE` statement | Flag for DBA review — prefer `UPDATE` + `INSERT` with `EXISTS` |
| `GEN-11` | Scalar UDF invoked in SELECT/WHERE/JOIN | Pre-2019: row-by-row, kills parallelism. 2019+: verify inlining |
| `GEN-12` | Cursor declared without `LOCAL FAST_FORWARD READ_ONLY` | Add options; consider set-based rewrite |

---

### Step 4c: Security Checks

| Rule | Pattern | Severity | Fix |
|------|---------|----------|-----|
| `SEC-1` | Dynamic SQL by string concatenation | HIGH | Use `sp_executesql` with typed parameters |
| `SEC-2` | `EXEC` on unvalidated string variable | HIGH | Parameterize all user-supplied values |
| `SEC-3` | `GRANT` inside procedure/migration without justification | MEDIUM | Flag for security review |
| `SEC-4` | `WITH EXECUTE AS` or `EXECUTE AS USER/LOGIN` | MEDIUM | Flag for DBA review |
| `SEC-5` | Cross-database reference without full qualification | MEDIUM | Use `[database].[schema].[table]` |
| `SEC-6` | Missing schema prefix on object reference | LOW | Always qualify with schema |
| `SEC-7` | `TRUNCATE TABLE` on `HIGH`/`CRITICAL` table | CRITICAL | Requires DBA sign-off |
| `SEC-8` | `DROP TABLE` / `DROP DATABASE` in migration | CRITICAL | Confirm data migrated/backed up |

---

### Step 5: Index Recommendations

After assessing risk and extracting the query pattern, evaluate whether the SQL:

- **Queries a HIGH/CRITICAL table without a matching index** → recommend `CREATE INDEX` with `ONLINE = ON` only if KB confirms Enterprise/Azure SQL
- **Creates an index that already exists or is redundant** → flag as redundant
- **Drops an index with active seeks** → categorical blocker
- **Creates an index without `ONLINE = ON`** on MEDIUM+ table when edition supports it → recommend adding it
- **Missing `INCLUDE` columns** to avoid key lookups → suggest adding them

Do **not** include `FILLFACTOR` below 100 in template DDL — only with measured page-split contention.

For HIGH/CRITICAL tables, also recommend `RESUMABLE = ON` (rebuilds: 2017+; creates: 2019+).

---

## Output Formats

| Flag | Behavior |
|------|---------|
| *(default / `--summary`)* | One-paragraph verdict + blocking issues only |
| `--full` | Full review: all sections, corrected SQL, scorecard |
| `--json` | Machine-readable JSON — one object per finding |
| `--gh-comment` | GitHub PR comment with `[!CAUTION]` / `[!WARNING]` / `[!NOTE]` |
| `--branch-diff <branch>` | Reviews full files changed vs `<branch>`, `--gh-comment` format |

---

## Important Rules

- NEVER display or store passwords — reference `$MSSQL_CONNECTION` by name only
- NEVER run DDL or DML — all recommended DDL is copy-paste only
- `ONLINE = ON` requires **Enterprise Edition or Azure SQL** — always check KB header
- `RESUMABLE = ON` requires SQL Server 2017+ for rebuilds, 2019+ for creates
- IQP features require Query Store **and** compat level 160
- Never recommend `FILLFACTOR < 100` as a default
- If KB is older than 30 days, warn at top of review output
- If referenced table is not in KB, mark risk as `UNKNOWN` and suggest `/sql-kb --refresh`
