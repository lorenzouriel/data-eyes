"""Register every tool family on the shared MCP server."""
from .registry import mcp
from . import discovery, query, history
from . import diagnostics

__all__ = ["mcp", "discovery", "query", "history", "diagnostics"]
