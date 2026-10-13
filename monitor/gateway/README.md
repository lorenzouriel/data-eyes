# Browser gateway

Nginx provides the shared browser entry point for Grafana and Streamlit. It routes dashboard requests to Grafana and checks the Grafana session before forwarding assistant requests and WebSocket handshakes to Streamlit. The assistant uses the shared ui-agent MCP permissions.

See the [Data Eyes project guide](../../README.md) for architecture, setup, and development.
