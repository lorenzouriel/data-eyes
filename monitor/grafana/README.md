# monitor/grafana

Grafana is the Data Eyes UI and does the alerting. It reads only the Data Eyes
Prometheus and never connects to SQL Server. The root
[docker-compose.yml](../../docker-compose.yml) mounts each part read-only.

| Path | Mounted at | Contents |
|---|---|---|
| [grafana.ini](grafana.ini) | `/etc/grafana/grafana.ini` | SMTP (from `GRAFANA_SMTP_*`), root URL, Fleet Overview as home dashboard, commented Azure AD sign-in example |
| [provisioning/](provisioning/) | `/etc/grafana/provisioning` | Datasource, dashboard provider, alert rules, contact point and policy |
| [dashboards/](dashboards/) | `/etc/grafana/dashboards` | Dashboard JSON |

Users, alert state and dashboard edits made in the UI live in the `grafana-data`
volume. Files here win on restart, so copy UI edits back into Git.

```powershell
docker compose restart grafana   # apply edits to these files
```

See [monitor/README.md](../README.md) for the dashboard sections, alert rules and
SMTP setup.

<!-- project-map:start -->
## Where this fits

- Reads only Prometheus, never SQL Server.
- Sends alert email with the SMTP settings from the root `.env`.
- The DBA's main screen: Fleet Overview is the home page.

```mermaid
flowchart LR
  dba(["DBA"])
  fleet[("SQL Server fleet")]
  inst["instances.yaml<br/>fleet + MCP principals"]
  login["mcp/sql<br/>monitoring login"]
  subgraph monitor["monitor/"]
    col["collector<br/>metrics + alert checks"]
    prom["prometheus<br/>30 days of history"]
    graf["grafana<br/>UI + alerting"]
  end
  mcp["mcp/<br/>MCP server, 27 tools"]
  agent["agent/<br/>Ask the fleet API"]
  subgraph claude[".claude/"]
    cmd["commands + agents"]
    kb["knowledge-base<br/>thresholds, taxonomy"]
    res["resources<br/>SQL toolkits + scripts"]
  end
  ci["GitHub Actions<br/>.github/workflows"]

  login -. "grants" .-> fleet
  inst --> col
  inst --> mcp
  col -- "read-only SQL" --> fleet
  prom -- "scrape /metrics" --> col
  graf -- "PromQL" --> prom
  graf -- "email alerts" --> dba
  dba --> graf
  mcp -- "diagnostic SQL" --> fleet
  mcp -- "severity history" --> prom
  agent -- "PromQL" --> prom
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
  class graf here
```

The highlighted box is this folder. Solid arrows are runtime calls; dotted arrows are configuration, mirrored rules, or manual use.

### In the repository

```text
data-eyes/
├── .claude/                                  Claude Code toolkit
├── .github/                                  GitHub configuration
├── agent/                                    "Ask the fleet" API
├── assets/                                   Logo
├── mcp/                                      MCP server (27 read-only tools)
├── monitor/                                  Collector -> Prometheus -> Grafana
│   ├── collector/                            SQL diagnostics exporter
│   ├── grafana/                              UI and alerting  ◀ you are here
│   │   ├── dashboards/                       Fleet Overview
│   │   └── provisioning/                     Applied at startup
│   └── prometheus/                           Scrape config, 30 days
├── .env.example                              Template for .env (Grafana, agent)
├── .mcp.json                                 Claude Code MCP registration (stdio, dev)
├── CLAUDE.md                                 Project instructions for Claude Code
├── README.md                                 Setup, configuration, security
├── docker-compose.yml                        The whole stack
└── instances.example.yaml                    Template for instances.yaml (fleet, MCP principals)
```
<!-- project-map:end -->
