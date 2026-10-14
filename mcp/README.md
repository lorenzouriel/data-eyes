# MCP monitoring server

The MCP server exposes nine read-only monitoring tools backed by Prometheus and authorized instance metadata. It authenticates callers and enforces tool, instance, and environment permissions. It serves the Data Eyes agent and external MCP clients without SQL credentials or a SQL connection.

See the [Data Eyes project guide](../README.md) for architecture, setup, and development.
