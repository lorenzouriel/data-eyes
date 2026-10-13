# Collector SQL permissions

These are manual templates for the collector's monitoring login. Review grants before
execution. Only the collector connects to SQL Server; MCP has no SQL login.

- `provision-readonly-login.sql`: base login and permissions.
- `provision-alerting-permissions.sql`: optional grants required by specific checks.

Configure SQL connection strings only in `instances.yaml`. Disable checks lacking the
required permissions in `monitor/collector/checks.yaml`.
