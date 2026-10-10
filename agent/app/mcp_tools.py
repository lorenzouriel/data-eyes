"""Live SQL diagnostics through the Data Eyes MCP servers.

The agent is an MCP client, like Claude Code. It connects to each configured
MCP environment (dev, staging, production) with its own bearer token as the
`ui-agent` principal, so SQL credentials, per-principal grants, limits and the
audit log all stay in the MCP servers. Only the diagnostic tools in
ALLOWED_TOOLS are offered to the model; the MCP server enforces the same grants
again. Environments whose container is not running are skipped.

Tools are exposed to the model as `sql_<tool>`. Each call is routed to the MCP
environment that serves the requested `instance`.
"""
import copy
import json
import logging
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Dict, List

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings

LOG = logging.getLogger("data_eyes_agent")

# Health diagnostics only. Excluded on purpose: sample_table / distinct_values
# (return table rows: business data to the model provider, and possible prompt
# injection), schema discovery, and index_fragmentation (reads every index page;
# expensive on large servers).
ALLOWED_TOOLS = (
    "wait_stats", "top_queries", "blocking_snapshot", "missing_indexes", "unused_indexes",
    "stale_statistics", "db_space", "backup_health", "checkdb_health", "ag_health", "job_health",
    "list_databases", "get_database_info",
)
PREFIX = "sql_"
CONNECT_TIMEOUT = 5
CALL_TIMEOUT = 60
MAX_RESULT_CHARS = 20_000


def servers() -> Dict[str, str]:
    """AGENT_MCP_SERVERS: "env=url,env=url" -> {env: url}."""
    result = {}
    for item in settings.AGENT_MCP_SERVERS.split(","):
        env, _, url = item.strip().partition("=")
        if env and url:
            result[env.strip()] = url.strip()
    return result


async def _reachable(url: str) -> bool:
    """Probe the server's public /health first. A stopped environment must be
    skipped before an MCP session starts: the client library reports connection
    failures by cancelling the pending request, which would end the question."""
    health = url.rsplit("/mcp", 1)[0] + "/health"
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            return (await client.get(health)).status_code == 200
    except httpx.HTTPError:
        return False


def _text(result) -> str:
    return "\n".join(getattr(part, "text", "") for part in result.content if getattr(part, "text", None))


class McpTools:
    """Sessions to the reachable MCP environments for one question."""

    def __init__(self):
        self._stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        self.instance_env: Dict[str, str] = {}
        self.tools: Dict[str, dict] = {}  # model-facing name -> {description, schema}

    async def __aenter__(self):
        if not settings.AGENT_MCP_TOKEN:
            return self
        headers = {"Authorization": f"Bearer {settings.AGENT_MCP_TOKEN}"}
        for env, url in servers().items():
            if not await _reachable(url):
                LOG.info("MCP environment skipped env=%s reason=unreachable", env)
                continue
            sub = AsyncExitStack()
            try:
                read, write, _ = await sub.enter_async_context(
                    streamablehttp_client(url, headers=headers, timeout=CONNECT_TIMEOUT, sse_read_timeout=CALL_TIMEOUT))
                session = await sub.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT)))
                await session.initialize()
                listing = await session.list_tools()
                instances = self._instances(_text(await session.call_tool("list_configured_instances", {})))
            except Exception as exc:  # not running, unreachable, or token not accepted
                LOG.info("MCP environment skipped env=%s error=%s", env, type(exc).__name__)
                await sub.aclose()
                continue
            self._stack.push_async_exit(sub)
            self.sessions[env] = session
            for name in instances:
                self.instance_env.setdefault(name, env)
            for tool in listing.tools:
                if tool.name in ALLOWED_TOOLS and PREFIX + tool.name not in self.tools:
                    self.tools[PREFIX + tool.name] = {"description": tool.description or tool.name,
                                                      "schema": tool.inputSchema or {"type": "object", "properties": {}}}
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    @staticmethod
    def _instances(text: str) -> List[str]:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return []
        rows = body.get("rows", body) if isinstance(body, dict) else body
        return [row["name"] for row in rows if isinstance(row, dict) and row.get("name")]

    def definitions(self) -> List[dict]:
        """Tool definitions for the model: `instance` is required and limited
        to the instances the running MCP environments serve."""
        available = sorted(self.instance_env)
        result = []
        for name, tool in self.tools.items():
            schema = copy.deepcopy(tool["schema"])
            schema.setdefault("properties", {})["instance"] = {
                "type": "string", "enum": available, "description": "Instance to run the diagnostic on"}
            schema["required"] = sorted(set(schema.get("required", [])) | {"instance"})
            summary = tool["description"].strip().split("\n\n")[0]
            result.append({"name": name, "schema": schema, "status": f"Running {name[len(PREFIX):]} on the server",
                           "description": f"[Live SQL diagnostic; runs a query on the server] {summary}"})
        return result

    def handles(self, name: str) -> bool:
        return name in self.tools

    async def run(self, name: str, arguments: dict) -> str:
        instance = (arguments or {}).get("instance")
        env = self.instance_env.get(instance or "")
        if env is None:
            return json.dumps({"error": f"instance {instance!r} is not served by a running MCP environment; "
                                        f"live diagnostics are available for {sorted(self.instance_env)}. "
                                        "Use the Prometheus tools for other instances."})
        try:
            result = await self.sessions[env].call_tool(name[len(PREFIX):], arguments)
        except Exception as exc:
            return json.dumps({"error": f"MCP call failed ({type(exc).__name__})"})
        text = _text(result) or "(no output)"
        if result.isError:
            text = json.dumps({"error": text[:2000]})
        return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "\n[truncated]"
