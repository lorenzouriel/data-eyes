"""Query implementation."""

from typing import Optional
from mcp.server.fastmcp import Context
from data_eyes_mcp.database.client import check_connection
from data_eyes_mcp.database.client import request_credentials
from data_eyes_mcp.observability.metrics import MetricsContext
from data_eyes_mcp.security.policy import explain_policy
from data_eyes_mcp.security.authorization import audit
from data_eyes_mcp.security.authorization import authorize
from data_eyes_mcp.transport.context import _connection_options
from data_eyes_mcp.tools.registry import mcp
import logging
logger = logging.getLogger(__name__)


@mcp.tool()
async def execute_sql(
    sql: str,
    format: str = "table",
    timeout: Optional[int] = None,
    max_rows: Optional[int] = None,
    database: Optional[str] = None,
    instance: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """Ad-hoc SQL is disabled. Use fixed diagnostic and discovery tools.

    Retained as an explicit denial for existing clients. No environment or
    write-mode setting can bypass this gate.
    """
    with request_credentials(**_connection_options(ctx, instance)):
        audit("deny", "adhoc_disabled", tool="execute_sql")
    return "ERROR: Ad-hoc SQL is disabled; use fixed diagnostic and discovery tools"


@mcp.tool()
async def get_policy_info(ctx: Optional[Context] = None) -> str:
    """
    Get current policy and safety settings.

    Returns:
        JSON-formatted policy information
    """
    tool_name = "get_policy_info"

    with MetricsContext(tool_name) as metrics:
        try:
            with request_credentials(**_connection_options(ctx, None)):
                authorize(tool=tool_name)
                policy = explain_policy()
            metrics.set_rows(1)

            import json
            return json.dumps(policy, indent=2)

        except Exception as e:
            logger.exception("get_policy_info failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def check_db_connection(instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Check if the database connection is active and healthy.

    Returns:
        Connection status message
    """
    tool_name = "check_db_connection"

    with MetricsContext(tool_name) as metrics:
        try:
            with request_credentials(**_connection_options(ctx, instance)):
                is_connected = await check_connection()
            metrics.set_rows(1)

            if is_connected:
                return "✓ Database connection is healthy"
            else:
                return "✗ Database connection failed"

        except Exception as e:
            logger.exception("check_db_connection failed")
            return f"ERROR: Database connection check failed - {str(e)}"
