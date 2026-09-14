"""
MCP Server bootstrap and transport selection.

Handles server initialization, transport selection (stdio vs HTTP),
and lifecycle management.
"""

import asyncio
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import settings, validate_settings
from .logging_config import setup_logging, get_logger
from .health import health_check, readiness_check, get_server_info, get_metrics_endpoint
from .tools import mcp as tools_mcp
from . import dba_tools  # noqa: F401 — import registers the DBA diagnostic tools on tools_mcp
from . import repository_tools  # noqa: F401 — import registers the dashboard-repository trend tools

logger = get_logger(__name__)


class MSSQLMCPServer:
    """Main MCP server class."""

    def __init__(self):
        self.mcp = None
        self.logger = get_logger(__name__)

    def setup(self) -> None:
        """Initialize server setup."""
        # Setup logging first
        setup_logging()

        self.logger.info("Starting Data Eyes MCP Server v0.1.0")

        # Validate configuration
        is_valid, error = validate_settings()
        if not is_valid:
            self.logger.error("Configuration validation failed: %s", error)
            raise ValueError(error)

        self.logger.info("Configuration validated successfully")
        self.logger.info("Mode: %s", "read-only" if settings.READ_ONLY else "write-enabled")
        self.logger.info("Transport: %s", settings.MCP_TRANSPORT)

    async def run(self) -> None:
        """
        Run the server.

        Selects transport (stdio or HTTP) and starts the server.
        """
        self.setup()

        if settings.MCP_TRANSPORT == "stdio":
            await self._run_stdio()
        elif settings.MCP_TRANSPORT == "http":
            await self._run_http()
        else:
            raise ValueError(f"Unknown transport: {settings.MCP_TRANSPORT}")

    async def _run_stdio(self) -> None:
        """Run server with stdio transport."""
        self.logger.info("Starting MCP server with stdio transport")

        # The tools_mcp from tools.py is a FastMCP instance
        # Use run_stdio_async() since we're already in an async context
        await tools_mcp.run_stdio_async()

    async def _run_http(self) -> None:
        """Run server with HTTP transport."""
        self.logger.info(
            "Starting MCP server with HTTP transport on %s:%d",
            settings.HTTP_BIND_HOST,
            settings.HTTP_BIND_PORT,
        )

        try:
            from starlette.responses import Response, JSONResponse
            from starlette.requests import Request

            # Configure FastMCP with the desired host and port
            tools_mcp.settings.host = settings.HTTP_BIND_HOST
            tools_mcp.settings.port = settings.HTTP_BIND_PORT

            # Register custom health and metrics endpoints on the FastMCP app
            # These will be available alongside the MCP protocol endpoint
            @tools_mcp.custom_route("/health", methods=["GET"])
            async def health_endpoint(request: Request) -> Response:
                """Liveness probe."""
                result = await health_check()
                return JSONResponse(result)

            @tools_mcp.custom_route("/ready", methods=["GET"])
            async def ready_endpoint(request: Request) -> Response:
                """Readiness probe."""
                result = await readiness_check()
                status_code = 200 if result["status"] == "ready" else 503
                return JSONResponse(result, status_code=status_code)

            @tools_mcp.custom_route("/info", methods=["GET"])
            async def info_endpoint(request: Request) -> Response:
                """Server information."""
                result = await get_server_info()
                return JSONResponse(result)

            @tools_mcp.custom_route("/metrics", methods=["GET"])
            async def metrics_endpoint(request: Request) -> Response:
                """Prometheus metrics."""
                metrics_text = await get_metrics_endpoint()
                return Response(metrics_text, media_type="text/plain")

            # Use FastMCP's built-in HTTP transport runner
            # This starts uvicorn with the Starlette app
            # MCP protocol is available at http://host:port/mcp
            await tools_mcp.run_streamable_http_async()

        except ImportError as e:
            self.logger.error("Required dependencies not installed: %s", e)
            raise


def create_server() -> MSSQLMCPServer:
    """
    Factory function to create and configure the MCP server.

    Returns:
        Configured MSSQLMCPServer instance
    """
    return MSSQLMCPServer()


async def main() -> None:
    """Main entry point."""
    server = create_server()
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.exception("Server error: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
