---
name: sql-guidelines
description: SQL Server clean code reviewer — checks naming conventions, formatting, and readability against Data Eyes guidelines
---

# /sql-guidelines Command

> Review SQL against the Data Eyes clean code guidelines and return actionable feedback

## Usage

```
/sql-guidelines <paste your SQL query or object definition here>
```

## Examples

```
/sql-guidelines SELECT * FROM Customers WHERE ID = 1
/sql-guidelines "CREATE TABLE Orders (ID INT PRIMARY KEY, CustID INT)"
/sql-guidelines "select c.name, o.id, o.total from customer c join order o on c.id = o.customer_id where o.total > 1000"
/sql-guidelines "CREATE PROCEDURE GetCustomer AS BEGIN SELECT * FROM customer END"
/sql-guidelines "CREATE INDEX idx_email ON customer(email_address)"
```

---

## What This Skill Does

1. Parses the submitted SQL (query, DDL, or object definition)
2. Evaluates it against each guideline category in order
3. Flags every violation with a clear label, the offending token, and a corrected version
4. Outputs the fully corrected SQL as a copy-paste block
5. Adds a pass/fail summary scorecard at the end

---

## Guideline Categories

### 1. Naming Conventions

#### Tables — singular noun, snake_case
- Use singular nouns: `customer` not `customers`, `order` not `orders`
- snake_case only: `order_item` not `OrderItem` or `orderItem`

#### Columns — snake_case
- All column names must be snake_case: `first_name`, `email_address`, `order_date`
- No CamelCase, PascalCase, or abbreviations without context

#### Primary Keys — `[entity]_id`
- Must follow pattern: `customer_id`, `order_id`, `product_id`
- Never just `id` or `ID`

#### Foreign Keys — `[referenced_entity]_id`
- Must use the referenced table's name: `customer_id` on the `order` table
- Constraint name: `fk_[table]_[referenced_table]` → `fk_order_customer`

#### Stored Procedures — `sp_[verb]_[entity]`
- Examples: `sp_get_customer`, `sp_update_payment`, `sp_delete_order`
- Verb must be meaningful: get, create, update, delete, list, process

#### Views — `vw_[entity]_[purpose]`
- Examples: `vw_order_summary`, `vw_payment_last_year`

#### Indexes
- Unique index: `ix_[table]_[column]` → `ix_customer_email`
- Non-unique index: `nix_[table]_[column]` → `nix_order_date`

#### Constraints — `ck_[table]_[rule]`
- Examples: `ck_order_total_positive`, `ck_payment_status_enabled`

---

### 2. Code Formatting & Readability

- **Capitalize all SQL keywords**: SELECT, FROM, WHERE, JOIN, ON, GROUP BY, ORDER BY, etc.
- **One clause per line**: FROM on its own line, WHERE on its own line, ORDER BY on its own line
- **One column per line** in SELECT lists (indent 4 spaces)
- **Indent 4 spaces** for all continuation lines
- **Meaningful aliases**: `c` for `customer`, `o` for `order`, `p` for `payment`
- **Separate logical blocks with a blank line**: after SELECT list, after FROM/JOINs, after WHERE
- **Use `AS` keyword** for aliases: `FROM customer AS c`, not `FROM customer c`

---

### 3. Avoid SELECT *

- Never use `SELECT *` — always list columns explicitly
- Exception: inside `EXISTS` sub-queries is acceptable

---

### 4. Comments

- Comments must explain **why**, not what the code does
- A comment that restates the SQL (e.g., `-- Select customers`) is a violation
- Stored procedures and views must include a header block:

```sql
-- Owner: <author>
-- Description: <business reason for this object>
-- Created: <YYYY-MM-DD>
```

- Inline comments are optional but must add non-obvious context

---

## Review Process

### Step 1: Parse the Input

Identify what type of SQL was submitted:
- `SELECT` query → check formatting, aliases, SELECT *, comments
- `CREATE TABLE` / `ALTER TABLE` → check naming (table, columns, PK, FK, constraints)
- `CREATE PROCEDURE` → check naming, formatting, header comment
- `CREATE VIEW` → check naming, formatting, header comment
- `CREATE INDEX` → check naming pattern (ix_ / nix_)

### Step 2: Evaluate Each Category

Go through every category in order. For each violation found:

| Field | What to write |
|---|---|
| **Category** | Naming / Formatting / SELECT * / Comments |
| **Rule** | The specific rule that was broken |
| **Offending token** | Exact text from the submitted SQL |
| **Fix** | What it should be instead |

### Step 3: Output the Corrected SQL

Rewrite the submitted SQL applying every fix. Present it as a single copy-paste block.

If no violations are found, say so explicitly and present the original SQL unchanged.

### Step 4: Scorecard

End with a compact scorecard:

```
--- Guideline Scorecard ---
Naming Conventions : PASS / FAIL (N violations)
Formatting         : PASS / FAIL (N violations)
Avoid SELECT *     : PASS / FAIL
Comments           : PASS / FAIL (N violations)
Overall            : PASS / FAIL
```

---

## Output Format

```
## Violations Found

### [Category] — [Rule]
- Offending: `<original token>`
- Fix: `<corrected token>`
- Reason: <one-line explanation>

---

## Corrected SQL

\`\`\`sql
<fully corrected SQL here>
\`\`\`

---

## Scorecard

Naming Conventions : ...
Formatting         : ...
Avoid SELECT *     : ...
Comments           : ...
Overall            : ...
```

---

## Important Rules

- Never silently fix violations — always list them before showing the corrected SQL
- If the SQL is a fragment (e.g., just a WHERE clause), review only the applicable categories and note which categories were skipped
- Do not invent aliases or column names that were not in the original SQL — use `[placeholder]` where context is missing
- If the submitted SQL is syntactically invalid, flag the syntax issue first before applying guideline checks
- The guideline uses snake_case; if the user's company uses a different case convention, note it but still apply snake_case as the default
