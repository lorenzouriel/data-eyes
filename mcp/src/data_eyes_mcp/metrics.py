"""
Metrics and observability module for Data Eyes MCP Server.

Exports Prometheus metrics for monitoring queries, performance, and errors.
"""

import logging
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

logger = logging.getLogger(__name__)

# Create a custom registry for our metrics
REGISTRY = CollectorRegistry()

# Counters
queries_executed_total = Counter(
    "mssql_queries_executed_total",
    "Total number of queries executed",
    ["tool_name", "status"],
    registry=REGISTRY,
)

queries_blocked_total = Counter(
    "mssql_queries_blocked_total",
    "Total number of queries blocked by policy",
    ["reason"],
    registry=REGISTRY,
)

errors_total = Counter(
    "mssql_errors_total",
    "Total number of errors",
    ["error_type"],
    registry=REGISTRY,
)

# Histograms
query_duration_seconds = Histogram(
    "mssql_query_duration_seconds",
    "Query execution duration in seconds",
    ["tool_name"],
    registry=REGISTRY,
)

query_rows_returned = Histogram(
    "mssql_query_rows_returned",
    "Number of rows returned per query",
    ["tool_name"],
    buckets=[1, 10, 100, 1000, 10000, 50000],
    registry=REGISTRY,
)

# Gauges
active_queries = Gauge(
    "mssql_active_queries",
    "Number of currently active queries",
    registry=REGISTRY,
)

active_connections = Gauge(
    "mssql_active_connections",
    "Number of active database connections",
    registry=REGISTRY,
)

server_ready = Gauge(
    "mssql_server_ready",
    "Server readiness (1 = ready, 0 = not ready)",
    registry=REGISTRY,
)


def record_query_success(tool_name: str, duration: float, rows: int):
    """Record successful query execution."""
    queries_executed_total.labels(tool_name=tool_name, status="success").inc()
    query_duration_seconds.labels(tool_name=tool_name).observe(duration)
    query_rows_returned.labels(tool_name=tool_name).observe(rows)


def record_query_error(tool_name: str, error_type: str, duration: float):
    """Record query error."""
    queries_executed_total.labels(tool_name=tool_name, status="error").inc()
    errors_total.labels(error_type=error_type).inc()
    query_duration_seconds.labels(tool_name=tool_name).observe(duration)


def record_query_blocked(reason: str):
    """Record blocked query."""
    queries_blocked_total.labels(reason=reason).inc()


def set_active_queries(count: int):
    """Update active queries gauge."""
    active_queries.set(count)


def set_server_ready(ready: bool):
    """Update server ready status."""
    server_ready.set(1 if ready else 0)


def get_metrics_text() -> str:
    """Get Prometheus metrics in text format."""
    from prometheus_client.exposition import REGISTRY as default_registry
    from prometheus_client import generate_latest
    return generate_latest(REGISTRY).decode("utf-8")


class MetricsContext:
    """Context manager for tracking metrics around an operation."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.start_time = None
        self.error_type = None
        self.rows = 0

    def __enter__(self):
        import time
        self.start_time = time.time()
        active_queries.inc()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.time() - self.start_time
        active_queries.dec()

        if exc_type is not None:
            error_type = exc_type.__name__
            record_query_error(self.tool_name, error_type, duration)
        else:
            record_query_success(self.tool_name, duration, self.rows)

        return False  # Don't suppress exceptions

    def set_rows(self, count: int):
        """Set the number of rows returned."""
        self.rows = count
