# sql_docker

A Docker Compose file for running SQL Server 2022 locally, for example as a lab
instance for Data Eyes.

| File | Contents |
|---|---|
| [docker-compose.yml](docker-compose.yml) | One `mssql` service: SQL Server 2022 Standard, Agent enabled, host port `14330`, 8 GB and 4 CPU limits, data, logs and backups in `./mnt/mssql-data` |
| `gitignore` | Ignores `mnt/*`. Rename it to `.gitignore` if you copy the folder elsewhere |

```powershell
docker compose -f .claude/resources/sql-scripts/sql_docker/docker-compose.yml up -d
```

Set your own `sa` password before starting it. Never reuse a real one or commit it.
To monitor this instance, add it to `instances.yaml` with a login from
[monitor/collector/sql/](../../../../monitor/collector/sql/).

<!-- project-map:start -->
## Where this fits

- Part of the script library under `.claude/resources/sql-scripts/`, routed by the `/sql-scripts` command.
- Nothing here runs on its own. A DBA, `/sql-scripts` or the `sql-server-dba` agent picks a script and runs it against a server in the fleet.
- A lab instance: add it to `instances.yaml` and the whole stack (collector, Grafana, MCP) monitors it.

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
  class res,fleet here
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
│           ├── index/                        Create, rebuild, inspect indexes
│           ├── lock/                         Sessions and blocking
│           ├── query_store/                  Query Store analysis
│           ├── server/                       Instance info, linked servers
│           ├── sql_access/                   Logins, users, permissions
│           ├── sql_agent/                    Agent jobs and sessions
│           ├── sql_docker/                   Local SQL Server 2022  ◀ you are here
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
