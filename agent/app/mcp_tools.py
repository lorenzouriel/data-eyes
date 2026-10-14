"""
MCP monitoring client. All measurements come from the collector via Prometheus.
"""
import copy
import json
import logging
import re
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Dict, List

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings

LOG = logging.getLogger("data_eyes_agent")

ALLOWED_TOOLS = ("fleet_overview", "instance_checks", "list_metrics", "query_metric", "metric_history",
                 "get_latest_snapshot", "get_severity_trend", "list_databases")
CONNECT_TIMEOUT = 5
CALL_TIMEOUT = 60
MAX_RESULT_CHARS = 100_000


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
        self.instance_env: Dict[str, list] = {}
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
            self.instance_env[env] = instances
            for tool in listing.tools:
                if tool.name in ALLOWED_TOOLS:
                    # Namespace every tool so global fleet queries retain environment scope.
                    name = re.sub(r"[^a-zA-Z0-9_]", "_", env) + "_" + tool.name
                    if name in self.tools:
                        raise ValueError("MCP environment tool names collide")
                    self.tools[name] = {"description": tool.description or tool.name,
                                        "schema": tool.inputSchema or {"type": "object", "properties": {}},
                                        "environment": env, "remote_name": tool.name}
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    @staticmethod
    def _instances(text: str) -> List[str]:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return []
        rows = body.get("rows", []) if isinstance(body, dict) else body
        if not isinstance(rows, list):
            return []
        return [row["name"] for row in rows if isinstance(row, dict) and row.get("name")]

    def definitions(self) -> List[dict]:
        result = []
        for name, tool in self.tools.items():
            schema = copy.deepcopy(tool["schema"])
            env = tool["environment"]
            if "instance" in schema.get("properties", {}):
                available = sorted(self.instance_env[env])
                if not available:
                    continue
                schema["properties"]["instance"] = {"type": "string", "enum": available}
            result.append({"name": name, "schema": schema,
                           "status": f"Reading {env} monitoring data",
                           "description": f"[{env}; collected metrics, no live SQL] {tool['description']}"})
        return result

    def handles(self, name: str) -> bool:
        return name in self.tools

    async def run(self, name: str, arguments: dict) -> str:
        tool = self.tools.get(name)
        if not tool:
            return json.dumps({"error": "Unknown monitoring tool"})
        if not isinstance(arguments, dict):
            return json.dumps({"error": "Tool arguments must be an object"})
        env = tool["environment"]
        if "instance" in tool["schema"].get("properties", {}):
            if arguments.get("instance") not in self.instance_env[env]:
                return json.dumps({"error": "Instance is not available in this MCP environment"})
        try:
            result = await self.sessions[env].call_tool(tool["remote_name"], arguments)
        except Exception as exc:
            return json.dumps({"error": f"Monitoring call failed ({type(exc).__name__})"})
        text = _text(result) or json.dumps({"error": "No monitoring output"})
        if len(text) > MAX_RESULT_CHARS:
            return json.dumps({"error": "Monitoring response too large; narrow the request"})
        return text
