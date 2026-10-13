# Grafana and assistant gateway

The browser entry point remains `http://localhost:3000`. Grafana and Streamlit
are internal services. The Ask the fleet dashboard embeds `/assistant/?embed=true`.
The Fleet Overview dashboard links to it. No public port 8501 is needed.

The gateway verifies the Grafana session cookie through `/api/user` before every
assistant HTTP request and WebSocket handshake. Anonymous Grafana access is disabled;
Basic/Bearer headers are not accepted as a substitute for a browser session on the
assistant route. A signed-out request receives 401. Already-established WebSockets
are authorized at connection time; logout takes effect for new requests/connections.

All signed-in Grafana users can use the assistant with the shared `ui-agent` MCP
permissions. This is not a per-user SQL or MCP permission mapping. Keep that shared
principal scoped to the fleet your Grafana users are allowed to inspect.

## HTTPS deployment

Point the existing HTTPS proxy/tunnel for `monitor.lorenzo.com.br` to the gateway
on port 3000, rather than the internal Grafana container. Forward the complete URI,
Host, X-Forwarded-Proto=https, Upgrade and Connection headers. Both `/` and
`/assistant/` must use that same upstream. TLS stays at the existing external proxy;
this repository does not provision certificates or change DNS/tunnel configuration.
Grafana's existing root_url is preserved. Streamlit's base URL path is `assistant`.

Streamlit CORS/XSRF protections remain enabled. Nginx supports WebSocket upgrades
and disables buffering on the assistant route. Only same-origin framing is allowed
for the assistant. Grafana's allow_embedding setting is not needed: Grafana is the
parent page, not the embedded page.

The HTML Text panel requires `GF_PANELS_DISABLE_SANITIZE_HTML=true`, which is an
instance-wide setting. Only trusted users should have dashboard edit permissions.
The supplied assistant dashboard is provisioned and not editable in the UI.

## Run and verify

```powershell
docker compose up -d gateway grafana agent-ui
docker compose exec gateway nginx -t
uv run --project agent python scripts/verify_grafana_embed.py
```

Run verification from the repository root. It reads the existing Grafana credentials
from `.env` without printing them, creates a temporary login session, checks dashboard
provisioning and authenticated HTTP/WebSocket access, then logs out that session.
It does not send an agent question or call a model provider.

For standalone local Streamlit development, the command in `agent/README.md` still
runs on localhost:8501 without the Compose gateway; that development process has no login.
