---
name: sql-visual-report
description: Generate a self-contained HTML report visualizing SQL Server performance tuning, maintenance operations, and index changes with SQL Server red (#CC2927) and Grafana orange (#F46800) brand colors
---

# /sql-visual-report Command

> Generate a visual HTML report for SQL Server performance tuning and maintenance changes

## Usage

```bash
/sql-visual-report                              # Report from current session context
/sql-visual-report "performance tuning session"  # With description
/sql-visual-report --branch-diff main            # From git diff of SQL files
/sql-visual-report --kb exampleDB              # KB-driven report with volume context
```

## Examples

```bash
/sql-visual-report "Diagnosed CPU spike — CXPACKET waits, raised cost threshold"
/sql-visual-report "Set up Ola Hallengren maintenance for production"
/sql-visual-report "Index optimization — created 3, dropped 2 unused"
/sql-visual-report --branch-diff main "Index changes for delivery table"
```

---

## What This Skill Does

1. Collects DBA actions from the current session (or git diff)
2. Loads knowledge base for volume context if available
3. Generates a **self-contained HTML page** with SQL Server and Grafana branding
4. Visualizes before/after baselines, index changes, config diffs, and maintenance schedules
5. Writes to `docs/reports/` and opens in browser

---

## Brand Colors

The report uses SQL Server and Grafana brand colors throughout:

```css
:root {
    /* SQL Server — primary accent */
    --sql-red: #CC2927;
    --sql-red-light: #F5E6E6;
    --sql-red-dark: #8B1A19;

    /* Grafana — secondary accent */
    --grafana-orange: #F46800;
    --grafana-orange-light: #FFF0E5;
    --grafana-orange-dark: #B34E00;

    /* Neutrals */
    --bg-primary: #FAFAFA;
    --bg-card: #FFFFFF;
    --bg-code: #F5F5F5;
    --text-primary: #1A1A1A;
    --text-secondary: #666666;
    --border: #E0E0E0;

    /* Status colors */
    --status-good: #2E7D32;
    --status-warn: #F9A825;
    --status-critical: #CC2927;
    --status-info: #1565C0;

    /* Before/After */
    --before-bg: #FFF0E5;
    --before-border: #F46800;
    --after-bg: #E8F5E9;
    --after-border: #2E7D32;
}
```

---

## Process

### Step 1: Gather Data

Depending on invocation mode:

**Session mode (default):**
- Mine current conversation for:
  - Performance findings (wait types, missing indexes, query fixes)
  - Configuration changes (MAXDOP, cost threshold, max memory)
  - Index operations (CREATE, DROP, REBUILD, REORGANIZE)
  - Maintenance setup (Ola Hallengren jobs, schedules, retention)
  - Before/after metrics (if Step 9 verify was done)

**Branch diff mode (`--branch-diff`):**
```bash
git diff --name-status <branch>...HEAD -- "*.sql"
git diff <branch>...HEAD -- "*.sql"
```
- Parse added/modified SQL files for DDL operations
- Categorize: index changes, schema changes, maintenance scripts, config changes

**KB mode (`--kb <database>`):**
- Load `.claude/knowledge-base/<database>.md`
- Include volume context for all referenced tables
- Show index health summary (missing, unused, existing)

### Step 2: Categorize Changes

Group all collected changes into these categories:

| Category | Icon | Color | What to include |
|----------|------|-------|-----------------|
| Performance Diagnosis | `🔍` | `--sql-red` | Wait stats findings, bottleneck identification, methodology step |
| Configuration Changes | `⚙️` | `--grafana-orange` | MAXDOP, cost threshold, max memory, Query Store, compat level |
| Index Operations | `📊` | `--sql-red` | CREATE/DROP/REBUILD with table volume, ONLINE/RESUMABLE status |
| Maintenance Setup | `🔧` | `--grafana-orange` | Ola Hallengren jobs, schedules, backup paths, retention |
| Schema Changes | `📋` | `--status-info` | ALTER TABLE, new columns, constraints, type changes |
| Query Fixes | `⚡` | `--status-good` | Before/after SQL with explanation of improvement |

### Step 3: Generate HTML

Generate a self-contained HTML page with these sections:

---

## Report Structure

### 1. Header Banner

SQL Server red gradient header with:
- Report title (from user description or auto-generated)
- Date and server/database name (from KB if available)
- SQL Server version and edition badge (from KB header)

```html
<header style="background: linear-gradient(135deg, #CC2927 0%, #8B1A19 100%); color: white;">
    <h1>SQL Server Performance Report</h1>
    <div class="badges">
        <span class="badge edition">Enterprise</span>
        <span class="badge version">SQL Server 2019</span>
        <span class="badge db">exampleDB</span>
    </div>
</header>
```

### 2. Executive Summary

One paragraph: what was done, why, and the outcome. Use Grafana orange accent for key metrics.

### 3. KPI Dashboard

Large hero numbers in a card grid:

| KPI | Source | Visual |
|-----|--------|--------|
| Tables Affected | Count from changes | SQL red card |
| Indexes Changed | CREATE + DROP + REBUILD count | Grafana orange card |
| Config Changes | Parameter count | Neutral card |
| Risk Level | From `/sql-pr-review` scoring | Color-coded badge |
| Estimated Impact | From missing index improvement scores | Green/amber card |
| KB Freshness | Days since KB generation | Green (< 30d) / Amber (> 30d) |

### 4. Performance Diagnosis (if applicable)

**Wait Statistics visualization:**
- Horizontal bar chart (pure CSS, no JS libraries) showing top wait types
- Color-coded: red for critical (> 30%), amber for significant (10-30%), green for normal (< 10%)
- Threshold labels from the 10-step methodology

**Before/After panels:**
- Side-by-side cards with `--before-bg` / `--after-bg` backgrounds
- Before: symptom, wait type distribution, baseline metrics
- After: fix applied, new wait distribution, improved metrics

### 5. Index Changes (if applicable)

**Table for each index operation:**

```html
<div class="index-card" style="border-left: 4px solid var(--sql-red);">
    <h4>CREATE INDEX [nix_delivery_status]</h4>
    <div class="table-badge critical">delivery — 36M rows — HIGH</div>
    <div class="details">
        <span class="key-cols">Key: status</span>
        <span class="include-cols">Include: created_at, session_id</span>
        <span class="options">ONLINE = ON, RESUMABLE = ON</span>
    </div>
    <div class="rationale">Missing index hint — improvement score: 35,094</div>
</div>
```

For DROP operations, show the usage stats that justified removal.

**Index Health Summary (from KB):**
- Total indexes, missing hints, unused candidates
- Mermaid diagram showing index coverage per high-volume table (optional)

### 6. Configuration Changes (if applicable)

Before/after table with Grafana orange accent:

```html
<table class="config-diff">
    <tr>
        <th>Parameter</th>
        <th class="before">Before</th>
        <th class="after">After</th>
        <th>Rationale</th>
    </tr>
    <tr>
        <td>cost threshold for parallelism</td>
        <td class="before">5</td>
        <td class="after">50</td>
        <td>90% of queries under cost 50 — reduces unnecessary parallelism</td>
    </tr>
</table>
```

### 7. Maintenance Schedule (if applicable)

Visual timeline/calendar showing the 7 Ola Hallengren jobs:

```
┌──────────────────────────────────────────────────┐
│  Weekly Schedule                                 │
├──────────┬───────────────────────────────────────┤
│ Daily    │ ██ 02:00 Full Backup                  │
│          │ ██ 06:00/18:00 Differential           │
│          │ ░░ Every 30min Transaction Log         │
│ Saturday │ ██ 01:00 Index Optimization            │
│          │ ██ 04:00 Statistics Update             │
│ Sunday   │ ██ 03:00 Integrity Check (CHECKDB)     │
└──────────┴───────────────────────────────────────┘
```

Built with CSS grid, SQL red for critical jobs, Grafana orange for optimization jobs.

### 8. SQL Changes (if applicable)

Before/after SQL blocks with syntax highlighting (pure CSS):
- SQL keywords: bold
- Strings: green
- Numbers: Grafana orange
- Comments: gray
- Changed lines: highlighted background

### 9. Volume Context (if KB loaded)

Table showing affected tables with volume classification:

| Table | Rows | Size | Classification | Indexes | Missing Hints |
|-------|------|------|----------------|---------|---------------|

Color-coded badges: red for CRITICAL, orange for HIGH, blue for MEDIUM, gray for SMALL.

### 10. Recommendations & Next Steps

Styled cards with severity indicators:
- Red left border: blocking actions
- Amber left border: recommended follow-ups
- Green left border: completed items
- Blue left border: informational notes

---

## HTML Requirements

- **Self-contained** — all CSS inline, no external dependencies
- **No JavaScript libraries** — vanilla JS only for interactivity (collapsible sections, sticky nav)
- **Responsive** — works on desktop and tablet
- **Print-friendly** — `@media print` styles included
- **Dark mode** — `prefers-color-scheme: dark` support with adjusted SQL red and Grafana orange
- **Sticky navigation** — sidebar or top nav for section jumping
- **Overflow protection** — `min-width: 0` on flex/grid children, `overflow-wrap: break-word`

### Dark Mode Colors

```css
@media (prefers-color-scheme: dark) {
    :root {
        --sql-red: #E85350;
        --sql-red-light: #3D1A1A;
        --grafana-orange: #FF8533;
        --grafana-orange-light: #3D2A1A;
        --bg-primary: #1A1A1A;
        --bg-card: #252525;
        --bg-code: #2D2D2D;
        --text-primary: #E0E0E0;
        --text-secondary: #999999;
        --border: #404040;
    }
}
```

---

## Output

1. Write HTML to `docs/reports/sql-report-{YYYY-MM-DD}.html`
   - If file exists, append timestamp: `sql-report-{YYYY-MM-DD}-{HHmm}.html`
2. If `docs/reports/` doesn't exist, create it
3. Open in browser:
   ```bash
   # Windows
   start docs/reports/sql-report-{date}.html
   # macOS
   open docs/reports/sql-report-{date}.html
   # Linux
   xdg-open docs/reports/sql-report-{date}.html
   ```
4. Print file path for user reference

---

## Important Rules

- NEVER include passwords, connection strings, or .env values in the report
- Server names and database names are OK — they are not secrets
- Volume data from KB is OK to display — it's metadata, not customer data
- Always include the KB generation date when showing volume data
- SQL code blocks should be sanitized (no credentials in connection strings)
- For `--branch-diff` mode, show full file content but annotate changed lines
- Include a footer with generation timestamp and Data Eyes version reference
