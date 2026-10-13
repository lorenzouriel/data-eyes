# index

Creating, maintaining and inspecting indexes.

| Script | What it does | Changes the server |
|---|---|---|
| [check_index_fragmentation.sql](check_index_fragmentation.sql) | Internal and external fragmentation of indexes on user tables | No |
| [statistics.sql](statistics.sql) | Operational usage statistics per table and index | No |
| [clustered_index.sql](clustered_index.sql) | Template: clustered index | Yes |
| [nonclustered_index.sql](nonclustered_index.sql) | Template: nonclustered index on one or more columns | Yes |
| [nonclustered_index_include.sql](nonclustered_index_include.sql) | Template: nonclustered index with `INCLUDE` columns | Yes |
| [clustered_columnstore_index.sql](clustered_columnstore_index.sql) | Template: clustered columnstore for analytics | Yes |
| [nonclustered_columnstore_index.sql](nonclustered_columnstore_index.sql) | Template: nonclustered columnstore on selected columns | Yes |
| [rebuild_index.sql](rebuild_index.sql) | `ALTER INDEX ... REBUILD` | Yes |
| [reorganize_index.sql](reorganize_index.sql) | `ALTER INDEX ... REORGANIZE` | Yes |
| [ola_hallengren.sql](ola_hallengren.sql) | Index optimization with Ola Hallengren's `IndexOptimize` | Yes |

## Before you change an index

- Name new indexes `ix_[table]_[col]` (unique) or `nix_[table]_[col]` (non-unique).
- `ONLINE = ON` needs Enterprise Edition.
- Rebuilding a large index takes locks and log space. Do it in a maintenance window.
- Measure the workload before you drop an index.

For live fragmentation with severity, use the `index_fragmentation` MCP tool.

<!-- project-map:start -->
## Where this fits

- Part of the script library under `.claude/resources/sql-scripts/`, routed by the `/sql-scripts` command.
- Nothing here runs on its own. A DBA, `/sql-scripts` or the `sql-server-dba` agent picks a script and runs it against a server in the fleet.
- The `missing_indexes`, `unused_indexes` and `index_fragmentation` MCP tools and collector checks find the candidates; these scripts act on them.

```mermaid
flowchart LR
  dba(["DBA"])
  fleet[("SQL Server fleet")]
  inst["instances.yaml<br/>collector SQL inventory"]
  login["monitor/collector/sql<br/>monitoring login"]
  subgraph monitor["monitor/"]
    col["collector<br/>metrics + alert checks"]
    prom["prometheus<br/>30 days of history"]
    graf["grafana<br/>UI + alerting"]
  end
  mcp["mcp/<br/>MCP monitoring tools"]
  agent["agent/<br/>Ask the fleet API"]
  subgraph claude[".claude/"]
    cmd["commands + agents"]
    kb["knowledge-base<br/>thresholds, taxonomy"]
    res["resources<br/>SQL toolkits + scripts"]
  end
  ci["GitHub Actions<br/>.github/workflows"]

  login -. "grants" .-> fleet
  inst --> col
  access["mcp-access.yaml<br/>metadata + grants"] --> mcp
  col -- "read-only SQL" --> fleet
  prom -- "scrape /metrics" --> col
  graf -- "PromQL" --> prom
  graf -- "email alerts" --> dba
  dba --> graf
  mcp -- "severity history" --> prom
  agent -- "MCP tools" --> mcp
  dba --> cmd
  cmd -- "MCP tools" --> mcp
  cmd --> kb
  cmd --> res
  kb -. "mirrored thresholds" .-> col
  kb -. "severity rules" .-> mcp
  res -. "run by hand" .-> fleet
  ci -. "test + build" .-> col
  ci -.-> mcp
  ci -.-> agent
  classDef here fill:#4a3aa7,stroke:#1baf7a,stroke-width:3px,color:#ffffff
  class res here
```

The highlighted box is this folder. Solid arrows are runtime calls; dotted arrows are configuration, mirrored rules, or manual use.

### In the repository

```text
data-eyes/
├── .claude/                                  Claude Code toolkit
│   ├── agents/                               sql-server-dba, dashboard-app
│   ├── commands/                             12 slash commands
│   ├── knowledge-base/                       Static KB + per-database KBs
│   └── resources/                            SQL toolkits and script library
│       ├── maintenance/                      Ola Hallengren playbooks and schedules
│       ├── performance/                      10-step tuning methodology, workbook
│       └── sql-scripts/                      84 scripts in 18 topics
│           ├── audit/                        SQL Server Audit
│           ├── backup_recovery/              Backups, restores, recovery models
│           ├── custom_alert_emails/          Database Mail job emails
│           ├── database_size/                Database, file and table sizes
│           ├── free_space/                   Reclaiming space, shrink
│           ├── functions/                    Custom functions
│           ├── helps/                        Helpers and templates
│           ├── index/                        Create, rebuild, inspect indexes  ◀ you are here
│           ├── lock/                         Sessions and blocking
│           ├── query_store/                  Query Store analysis
│           ├── server/                       Instance info, linked servers
│           ├── sql_access/                   Logins, users, permissions
│           ├── sql_agent/                    Agent jobs and sessions
│           ├── sql_docker/                   Local SQL Server 2022
│           ├── sql_profiler/                 Server-side traces
│           ├── ssis/                         SSIS jobs and SSISDB
│           ├── ssrs/                         ReportServer queries
│           └── triggers/                     Trigger examples
├── .github/                                  GitHub configuration
├── agent/                                    "Ask the fleet" API
├── assets/                                   Logo
├── mcp/                                      MCP monitoring tools
├── monitor/                                  Collector -> Prometheus -> Grafana
├── .env.example                              Template for .env (Grafana, agent)
├── .mcp.json                                 Claude Code MCP registration (stdio, dev)
├── CLAUDE.md                                 Project instructions for Claude Code
├── README.md                                 Setup, configuration, security
├── docker-compose.yml                        The whole stack
└── instances.example.yaml                    Template for collector SQL inventory
```
<!-- project-map:end -->
