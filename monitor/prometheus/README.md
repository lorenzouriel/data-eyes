# Prometheus

Prometheus scrapes cached collector metrics every 30 seconds and stores 30 days of history. Grafana and MCP query this shared measurement store. Recording rules derive rates and latency; Grafana owns alert evaluation and delivery.

See the [Data Eyes project guide](../../README.md) for architecture, setup, and development.
