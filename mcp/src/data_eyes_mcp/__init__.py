"""
Data Eyes MCP Server - MCP server for SQL Server database access.

This package provides a Model Context Protocol (MCP) server that safely exposes
database metadata and query capabilities to LLM-based clients.
"""

__version__ = "0.1.0"
__author__ = "Lorenzo Uriel"

from .config import settings
from .server import create_server

__all__ = ["settings", "create_server"]