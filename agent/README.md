# Ask the fleet agent

The agent answers questions about collected fleet health and performance. Its FastAPI service runs the model tool loop and invokes environment-scoped MCP tools; MCP reads Prometheus. A Streamlit chat client displays streamed progress and answers inside Grafana. Provider credentials stay in the API service.

See the [Data Eyes project guide](../README.md) for architecture, setup, and development.
