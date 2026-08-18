---
name: sync-context
description: Sync CLAUDE.md with current data-eyes structure — scripts, commands, agents, KB, and dashboard/MCP config
---

# /sync-context Command

> Analyze data-eyes codebase and update CLAUDE.md with current project state

## Usage

```bash
/sync-context                    # Full analysis and update
/sync-context --dry-run          # Preview changes without saving
/sync-context --section scripts  # Update specific section
```

---

## What It Does

1. **Scans** current repository structure (scripts, configs, dashboards)
2. **Counts** scripts per sub-folder and detects new additions
3. **Lists** available commands, agents, and KB files
4. **Merges** with existing CLAUDE.md — preserves manual sections
5. **Updates** auto-generated sections (structure, commands, inventory)

---

## Analysis Process

### Step 1: Scan Repository Structure

```text
# Core components
Glob("dashboard/**/*")
Glob("mcp/**/*")
Glob("performance/**/*")
Glob("maintenance/**/*")
Glob("sql-scripts/**/*.sql")

# .claude configuration
Glob(".claude/commands/data-eyes/*.md")
Glob(".claude/agents/*.md")
Glob(".claude/knowledge-base/*.md")

# Documentation
Glob("CLAUDE.md")
Glob("README.md")
Glob("**/README.md")
```

### Step 2: Count Script Inventory

For each sub-folder in `sql-scripts/`:
```text
Glob("sql-scripts/<subfolder>/*.sql")
```

Build inventory table with counts. Compare against CLAUDE.md if it exists — flag new sub-folders or scripts.

### Step 3: Extract Command and Agent Lists

Read frontmatter from each command file:
```text
Read(".claude/commands/data-eyes/<name>.md")  # first 5 lines for name + description
```

Read frontmatter from each agent file:
```text
Read(".claude/agents/<name>.md")  # first 10 lines for name + description + tier
```

### Step 4: Check Dashboard/MCP Configuration

```text
Read("dashboard/docker-compose.yml")        # services, ports
Read("dashboard/backend/instances.yaml")    # instance registry seed (names only)
Read("mcp/docker-compose.yml")              # agent-only MCP server, not used by the dashboard
Glob(".claude/knowledge-base/_static/*")    # static KB coverage
```

### Step 5: Check KB State

For each file in `.claude/knowledge-base/`:
- Extract generated date, server, edition, version from header
- Note staleness

### Step 6: Merge and Write

```text
1. Read existing CLAUDE.md (if present)
2. Parse into sections
3. Apply update rules (see table below)
4. Write updated CLAUDE.md
```

---

## Section Update Rules

| Section | Source | Update Mode |
|---------|--------|-------------|
| Project title + description | Manual | Preserve |
| Repository Structure | Glob scans | Replace |
| Key Conventions | Manual | Preserve |
| SQL Naming Standards | Manual | Preserve |
| Slash Commands | commands/ folder scan | Replace |
| Knowledge Base | .claude/knowledge-base/ scan | Replace |
| Safety Rules | Manual | Preserve |

**Replace**: Fully regenerate from source.
**Preserve**: Never auto-modify.

---

## CLAUDE.md Sections to Generate

### Repository Structure

Auto-generate directory tree from Glob results. Include file counts:

```markdown
## Repository Structure

\```
data-eyes/
├── dashboard/            backend ({N} routers), frontend, repository schema
├── mcp/                  data-eyes-mcp server, {N} DBA diagnostic tools
├── performance/          {N} scripts, {N} docs, workbook
├── maintenance/          {N} playbooks, {N} use cases
├── sql-scripts/          {N} scripts across {N} sub-folders
│   ├── audit/            {N} scripts
│   ├── backup_recovery/  {N} scripts
│   └── ...
└── .claude/
    ├── commands/         {N} commands
    ├── agents/           {N} agents
    └── knowledge-base/   {N} databases
\```
```

### Slash Commands Table

Auto-generate from command frontmatter:

```markdown
## Slash Commands

| Command | Purpose |
|---------|---------|
| `/document` | {description from frontmatter} |
| `/maintenance` | {description from frontmatter} |
| ...
```

### Knowledge Base Section

Auto-generate from KB files:

```markdown
## Knowledge Base

| Database | Generated | Server | Edition | Status |
|----------|-----------|--------|---------|--------|
| exampleDB | 2026-06-10 | na-shard1 | Developer | Fresh |
```

---

## Output

```text
SYNC CLAUDE.MD
━━━━━━━━━━━━━━

Scanning data-eyes...
✓ Found {N} SQL scripts across {N} sub-folders
✓ Found {N} commands, {N} agents
✓ Found {N} knowledge bases
✓ Monitor stack: {N} dashboards, {N} docs

Section updates:
• Repository Structure: UPDATED ({N} new scripts detected)
• Slash Commands: UPDATED ({N} commands)
• Knowledge Base: UPDATED ({N} databases)
• Key Conventions: PRESERVED (manual content)
• Safety Rules: PRESERVED (manual content)

━━━━━━━━━━━━━━
CLAUDE.md updated successfully
```

---

## When to Run

- After adding new SQL scripts to any sub-folder
- After creating new commands or agents
- After building a new knowledge base with `/sql-kb`
- After significant changes to dashboard/MCP configuration
- When onboarding team members
