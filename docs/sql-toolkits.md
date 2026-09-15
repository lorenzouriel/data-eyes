# SQL toolkits

Data Eyes includes operational resources alongside the deployable dashboard and
MCP system. These assets live under [`.claude/resources/`](../.claude/resources/)
and can be used manually in SQL Server tooling or selected by repository agent
workflows.

## Performance toolkit

Location: [`.claude/resources/performance/`](../.claude/resources/performance/)

The performance toolkit provides a structured investigation workflow, an Excel
workbook, diagnostic queries, and supporting guidance. Its central operating
principle is to establish a baseline, make one controlled change, and verify
the result.

The workflow covers:

1. preparation and baseline capture;
2. workload and expensive-query analysis;
3. contention and waits;
4. TempDB, memory, CPU, and I/O investigation;
5. configuration and indexing review;
6. before-and-after verification.

Use the toolkit for deliberate tuning work. Use the dashboard for continuous
visibility and MCP tools for live agent-assisted investigation.

Detailed usage: [Performance README](../.claude/resources/performance/README.md)

## Maintenance toolkit

Location: [`.claude/resources/maintenance/`](../.claude/resources/maintenance/)

The maintenance toolkit organizes backup, integrity-check, index, and
statistics routines around SQL Server Agent. It includes a playbook, a job
schedule, diagnostics, and use-case examples.

Several dashboard and MCP health checks read maintenance history from
`master.dbo.CommandLog`, which is normally created by Ola Hallengren's SQL
Server Maintenance Solution. Data Eyes does not silently install or execute
that solution; deployment is an explicit DBA operation.

Detailed usage: [Maintenance README](../.claude/resources/maintenance/README.md)

## SQL scripts library

Location: [`.claude/resources/sql-scripts/`](../.claude/resources/sql-scripts/)

The reusable script collection is organized by topic:

- auditing and access;
- backup, recovery, capacity, and free space;
- indexes, locking, Query Store, and server diagnostics;
- SQL Agent and custom alert email;
- Docker-hosted SQL Server;
- SSIS, SSRS, Profiler, functions, triggers, and helper scripts.

Scripts vary in risk and scope. Read each script before execution, verify the
target server and database, and test write-capable operations outside
production first.

Detailed catalog: [SQL scripts README](../.claude/resources/sql-scripts/README.md)

## Relationship to the application

The application and toolkits complement one another:

1. Dashboard trends identify a degraded category or instance.
2. MCP diagnostics or performance scripts investigate the cause.
3. A DBA reviews and applies an appropriate tuning or maintenance change.
4. Dashboard history validates whether health improved.

The monitoring path is read-oriented. The supporting toolkits may contain
write-capable maintenance statements and therefore require separate review and
authorization.
