"""
Command-line interface for Data Eyes MCP Server.

Provides CLI entry point with argument parsing.
"""

import asyncio
import argparse
import sys
import logging

from .server import create_server
from .config import settings
from .logging_config import setup_logging


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Data Eyes MCP Server - MCP server for SQL Server database access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with stdio transport (default)
  python -m data_eyes_mcp.cli

  # Run with HTTP transport
  python -m data_eyes_mcp.cli --transport http --bind 0.0.0.0:8080

  # Run with custom connection string
  MSSQL_CONNECTION_STRING="..." python -m data_eyes_mcp.cli

  # Run with debug logging
  python -m data_eyes_mcp.cli --log-level DEBUG
        """,
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mechanism (default: stdio)",
    )

    parser.add_argument(
        "--bind",
        type=str,
        default="127.0.0.1:8080",
        help="Bind address for HTTP transport (default: 127.0.0.1:8080)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        default="json",
        help="Log format (default: json)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def parse_bind_address(bind_str: str) -> tuple[str, int]:
    """Parse bind address string into host and port."""
    parts = bind_str.rsplit(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid bind address: {bind_str}. Expected format: host:port")

    host, port_str = parts
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"Invalid port: {port_str}")

    return host, port


async def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Apply CLI arguments to settings
    settings.MCP_TRANSPORT = args.transport
    settings.LOG_LEVEL = args.log_level
    settings.LOG_FORMAT = args.log_format

    if args.transport == "http":
        try:
            host, port = parse_bind_address(args.bind)
            settings.HTTP_BIND_HOST = host
            settings.HTTP_BIND_PORT = port
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        # Setup logging with parsed settings
        setup_logging()
        logger = logging.getLogger(__name__)

        logger.info("Data Eyes MCP Server starting...")
        logger.info("Transport: %s", settings.MCP_TRANSPORT)
        if settings.MCP_TRANSPORT == "http":
            logger.info("HTTP bind: %s:%d", settings.HTTP_BIND_HOST, settings.HTTP_BIND_PORT)

        # Create and run server
        server = create_server()
        await server.run()

        return 0

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1


def run() -> None:
    """Entry point for console script."""
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


if __name__ == "__main__":
    run()
