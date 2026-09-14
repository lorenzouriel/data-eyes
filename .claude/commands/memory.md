---
name: memory
description: Save valuable DBA session insights — debugging findings, config decisions, SQL Server gotchas
---

# /memory Command

> Save session insights to `.claude/storage/` for future reference

## Usage

```bash
/memory                           # Save current session insights
/memory "specific note to save"   # Save with specific context
```

---

## What It Does

1. **Analyzes** current conversation for valuable DBA insights
2. **Compresses** to high-signal format (decisions, patterns, gotchas)
3. **Saves** to `.claude/storage/memory-{YYYY-MM-DD}.md`

---

## When to Use

Save when you discover something worth remembering:

- Non-obvious SQL Server configuration decisions with rationale
- Performance tuning findings (which wait type, which fix worked)
- Index strategy decisions (why this index, why not that one)
- Maintenance schedule adjustments and reasons
- Monitoring threshold calibrations
- SQL Server version-specific gotchas
- KB observations (stale data, surprising volumes)

**Don't save:**

- Step-by-step script execution details (obvious from scripts)
- Temporary debugging output
- Every session (only valuable ones)

---

## Process

When invoked:

```text
1. Scan conversation for:
   - Decisions (look for "decided", "chose", "will use", "changed to")
   - Performance findings (wait types, index recommendations, query fixes)
   - Gotchas (look for "gotcha", "watch out", "careful", "don't", "never")
   - Config changes (MAXDOP, cost threshold, memory, maintenance schedules)
   - Open items (look for "TODO", "later", "next time", "follow up")

2. Compress ruthlessly:
   - Max 5 decisions
   - Max 3 performance findings
   - Max 3 gotchas
   - Max 3 open items

3. Write to storage:
   - Create .claude/storage/ if not exists
   - Append to existing file if same date
   - Use consistent format
```

---

## Output Format

Creates: `.claude/storage/memory-{YYYY-MM-DD}.md`

```markdown
# Memory: {date}

> {One-line summary of session}

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| {what} | {why} | {database/table/server affected} |

## Performance Findings

| Finding | Root Cause | Fix Applied | Result |
|---------|-----------|-------------|--------|
| {symptom} | {wait type / missing index / config} | {what changed} | {improvement} |

## Gotchas

- {gotcha}: {how to avoid}

## Open Items

- [ ] {item for next session}

---
*Saved: {timestamp}*
```

---

## Example

```text
User: /memory "Diagnosed CPU spike on na-shard1"

→ Scanning conversation...
→ Found: 1 decision, 2 performance findings, 1 gotcha

Saved to: .claude/storage/memory-2026-06-17.md

## Preview:
> Diagnosed CPU spike on na-shard1 — CXPACKET waits from low cost threshold

| Decision | Rationale |
|----------|-----------|
| Raised cost threshold to 50 | 90% of queries < 50 cost, were going parallel unnecessarily |

| Finding | Root Cause | Fix |
|---------|-----------|-----|
| 45% CXPACKET waits | Cost threshold at 5 (default) | Raised to 50 |
| eventTarget full scan | Missing index on eventTargetTypeID | Created nix_eventTarget_eventTargetTypeID |

Gotcha: DMV stats were only 2 days old after restart — wait for 2+ weeks before trusting unused index data
```
