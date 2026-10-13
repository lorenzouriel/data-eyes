# Agent

The agent answers monitoring questions using MCP tools backed by the collector's
Prometheus measurements. It does not connect to SQL Server or query Prometheus directly.

`Streamlit -> agent API -> MCP -> Prometheus <- collector <- SQL Server`

Configure the model provider and `AGENT_MCP_TOKEN` in the root `.env`. The token's
hash must belong to `ui-agent` in `mcp-access.yaml`. `AGENT_MCP_SERVERS` contains
comma-separated `environment=url` pairs. Stopped/unreachable environments are skipped;
if no tools are available, the agent reports monitoring unavailable.
Tools are namespaced by environment, with instance arguments restricted to discovered names.

The agent can explain health checks, collected performance measurements and trends.
It cannot inspect SQL text, sessions, plans, schema, or table rows. The system prompt
requires checking measurement freshness and reporting missing/stale data explicitly.

## Chat UI

```powershell
docker compose up -d --build gateway
```

Open http://localhost:3000/d/ask-the-fleet/ask-the-fleet and sign in to Grafana.
The gateway protects `/assistant/` using the Grafana session. Streamlit port 8501
is internal only. The UI shows model configuration, history, progress, and errors.
See [gateway deployment](../monitor/gateway/README.md) for HTTPS routing and access scope.
Provider keys stay in the API service. History is session-only; the latest 19 successful
exchanges are sent with the next question, with each message capped at 8000 characters.

Local development, in separate terminals from `agent/`:

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run streamlit run app/ui.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

Set `AGENT_MCP_SERVERS` to host-reachable MCP endpoints when running locally.
The UI uses `AGENT_API_URL`, default `http://localhost:8000`.

## API and source

| File | Responsibility |
|---|---|
| `app/main.py` | `/health`, `/api/agent/status`, `/api/agent/ask` (SSE) |
| `app/agent.py` | Model prompt and bounded tool loop |
| `app/mcp_tools.py` | MCP discovery, environment namespacing and calls |
| `app/config.py` | Provider configuration and monitoring token |
| `app/ui.py` | Streamlit chat |

`monitoring_configured` reports token configuration, not live connectivity.
Limits: `AI_MAX_TOOL_CALLS`, `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS`, `AI_MAX_CONCURRENT_ASKS`.

```powershell
uv run --project agent --frozen python -m unittest discover -s agent/tests -v
```
