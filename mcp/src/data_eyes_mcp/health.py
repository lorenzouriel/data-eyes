"""
Health checks and admin endpoints for Data Eyes MCP Server.

Provides HTTP endpoints for:
- /health (liveness probe)
- /ready (readiness probe)
- /metrics (Prometheus metrics)
- /info (server info)
"""

import logging
from typing import Dict, Any
from datetime import datetime

from .db import check_connection
from .config import settings
from .metrics import server_ready

logger = logging.getLogger(__name__)


async def health_check() -> Dict[str, Any]:
    """
    Liveness probe - check if server is running.

    Returns:
        Health status dict
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


async def readiness_check() -> Dict[str, Any]:
    """
    Readiness probe - check if server is ready to serve requests.

    Checks database connectivity and other dependencies.

    Returns:
        Readiness status dict
    """
    is_db_ready = await check_connection()
    is_ready = is_db_ready

    server_ready.set(1 if is_ready else 0)

    return {
        "status": "ready" if is_ready else "not_ready",
        "database_connected": is_db_ready,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def get_server_info() -> Dict[str, Any]:
    """
    Get server information and configuration.

    Returns:
        Server info dict
    """
    return {
        "name": "data-eyes-mcp",
        "version": "0.1.0",
        "transport": settings.MCP_TRANSPORT,
        "read_only": settings.READ_ONLY,
        "enable_writes": settings.ENABLE_WRITES,
        "metrics_enabled": settings.ENABLE_METRICS,
        "log_level": settings.LOG_LEVEL,
        "max_rows_per_query": settings.MAX_ROWS_PER_QUERY,
        "query_timeout_seconds": settings.MSSQL_QUERY_TIMEOUT,
    }


async def get_metrics_endpoint() -> str:
    """
    Get Prometheus metrics.

    Returns:
        Prometheus metrics in text format
    """
    from .metrics import get_metrics_text
    return get_metrics_text()
