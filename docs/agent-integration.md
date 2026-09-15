# Agent integration

The [`.claude/`](../.claude/) directory provides repository-aware workflows for
agents working with Data Eyes. It supports the application and SQL resources;
it is not required to run the Docker stack.

## Structure

| Area | Responsibility |
|---|---|
| `.claude/agents/` | Specialist roles for SQL Server work and dashboard development |
| `.claude/commands/` | Repeatable monitoring, tuning, documentation, and maintenance workflows |
| `.claude/knowledge-base/` | Static routing rules plus generated per-database knowledge |
| `.claude/resources/` | Performance, maintenance, and SQL script assets |

## Specialist agents

`sql-server-dba.md` routes SQL Server diagnosis, performance, and maintenance
work. It can use live Data Eyes MCP tools when available and fall back to the
repository's SQL resources where appropriate.

`dashboard-app.md` focuses on the React/FastAPI/PostgreSQL application,
including deployment, APIs, collection, and UI behavior.

## Commands

Commands cover tasks such as fleet status, SQL monitoring, performance
analysis, maintenance planning, script discovery, knowledge-base updates,
documentation, pull-request review, and visual reporting. They should reference
MCP tools by their current names and use the shared instance names from
`src/instances.yaml`.

## Knowledge base

The knowledge base separates compact cross-cutting references from deeper
per-database material:

- `_static/taxonomy.md` maps health categories, dashboard tabs, and diagnostic
  concepts.
- `_static/scripts-index.md` indexes reusable SQL resources.
- `_static/naming-conventions.md` keeps identifiers consistent.
- `_static/methodology.md` captures the performance workflow.
- generated per-database documents hold environment-specific knowledge.

See [`.claude/knowledge-base/README.md`](../.claude/knowledge-base/README.md)
for generation and maintenance rules.

## MCP registration

The root [`.mcp.json`](../.mcp.json) registers the local Data Eyes MCP server
from `src/mcp`. An MCP-capable client can therefore discover the same fleet
used by the dashboard without copying connection strings into each tool or
agent definition.

The recommended workflow is:

1. call `list_configured_instances`;
2. choose an explicit instance for live tools;
3. use read-only diagnostics to gather evidence;
4. correlate live evidence with repository trend tools;
5. propose write-capable maintenance separately for human review.

For tool details and security boundaries, see [MCP server](mcp.md).
