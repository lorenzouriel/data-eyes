# SQL Server collector

The collector is the only Data Eyes service that connects to SQL Server. It runs scheduled read-only queries and health checks, caches their results, and exposes them as Prometheus metrics. Separate concurrency lanes and persisted checkpoints keep collection bounded and independent of dashboard or chat requests.

See the [Data Eyes project guide](../../README.md) for architecture, setup, and development.
