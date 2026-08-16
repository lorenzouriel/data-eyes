"""
Thin MCP client for the dashboard backend.

Talks to each registered data-eyes-mcp instance (see instances.yaml) over the
MCP streamable-HTTP transport — the same server Claude Code talks to over
stdio via the repo's root .mcp.json, just a different transport, since stdio
is a single-process pipe and unsuitable for a persistent multi-client web
backend.

v1 opens a fresh MCP session per call rather than pooling persistent
connections per instance — simpler and correct, and fine for this backend's
polling cadence (15-30s per the rearchitecture plan). Revisit only if
per-call connection overhead becomes an actual bottleneck.
"""

import json
import logging
from typing import Any, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


class MCPToolError(Exception):
    """Raised when an MCP tool call fails or the server is unreachable."""


async def call_tool(
    mcp_url: str,
    tool_name: str,
    arguments: Optional[dict] = None,
    timeout: float = 15.0,
) -> Any:
    """
    Call a tool on a data-eyes-mcp server and parse its result.

    Every tool in this project's MCP server (mcp/src/data_eyes_mcp/tools.py,
    dba_tools.py) returns a single text content block — either a JSON string
    (parsed and returned as dict/list) or a short human-readable message
    (returned as-is). Trust between the dashboard backend and the MCP servers
    it's configured to talk to is implicit (same trusted Docker network) —
    there is no additional auth layer between them in v1.
    """
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True)
    try:
        async with http_client:
            async with streamable_http_client(mcp_url, http_client=http_client) as (
                read_stream,
                write_stream,
                _get_session_id,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments or {})

                    if result.isError:
                        message = _extract_text(result) or "unknown error"
                        raise MCPToolError(f"{tool_name} returned an error: {message}")

                    text = _extract_text(result)
                    if text is None:
                        return None
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return text
    except MCPToolError:
        raise
    except Exception as e:
        logger.warning("MCP call failed: tool=%s url=%s error=%s", tool_name, mcp_url, e)
        raise MCPToolError(f"Could not reach {mcp_url}: {e}") from e


def _extract_text(result) -> Optional[str]:
    """Pull the text out of a CallToolResult's first text content block, if any."""
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return None
