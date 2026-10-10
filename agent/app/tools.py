"""Read-only Prometheus tools for the agent.

Prometheus only holds the collector's metrics, so every tool is read-only by
construction. Limits keep a single question cheap: query timeouts, a cap on
series and points, a 30-day range, and a cap on the size of each result.
Label values (instance, database, file names) come from monitored servers and
are returned as data; the system prompt tells the model never to follow them.
"""
import json
import math
import time
from typing import Any, Awaitable, Callable, Dict, List

import httpx

from app.config import settings

MAX_SERIES = 100
MAX_POINTS = 120
MAX_RANGE_HOURS = 720
MAX_RESULT_CHARS = 20_000
QUERY_TIMEOUT = "15s"
SEVERITY = {0: "OK", 1: "UNKNOWN", 2: "WARNING", 3: "CRITICAL"}
DROP_LABELS = {"__name__", "job", "instance"}

CHECK_KEY = 'label_replace(data_eyes_health_severity, "check", "$1", "category", "alert\\\\.(.+)")'


class ToolError(Exception):
    """A tool failed in a way the model should see and can recover from."""


def lit(value: str) -> str:
    """PromQL string literal."""
    return json.dumps(str(value))


async def _api(client: httpx.AsyncClient, path: str, params: Dict[str, Any]) -> Any:
    response = await client.get(f"{settings.PROMETHEUS_URL}/api/v1/{path}", params={**params, "timeout": QUERY_TIMEOUT})
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or body.get("status") != "success":
        raise ToolError(body.get("error") or f"Prometheus returned HTTP {response.status_code}")
    return body["data"]


def _labels(metric: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in metric.items() if k not in DROP_LABELS}


def _number(text: str):
    value = float(text)
    return round(value, 4) if math.isfinite(value) else None


async def _instant(client, expr: str) -> List[dict]:
    data = await _api(client, "query", {"query": expr})
    if data["resultType"] == "scalar":
        return [{"labels": {}, "value": _number(data["result"][1])}]
    return [{"labels": _labels(r["metric"]), "value": _number(r["value"][1])} for r in data["result"]]


async def fleet_overview(client, **_) -> dict:
    """Every instance with reachability, overall severity and open-check counts."""
    def by_instance(rows):
        return {r["labels"].get("sql_instance"): r["value"] for r in rows}

    info = await _instant(client, "data_eyes_instance_info")
    severity = by_instance(await _instant(client, "data_eyes_overall_severity"))
    reachable = by_instance(await _instant(client, "data_eyes_sqlserver_reachable"))
    open_counts: Dict[str, Dict[str, int]] = {}
    for code, label in ((3, "critical"), (2, "warning"), (1, "unknown")):
        for row in await _instant(client, f"count by (sql_instance) (data_eyes_health_severity == {code})"):
            open_counts.setdefault(row["labels"]["sql_instance"], {})[label] = int(row["value"] or 0)
    instances = []
    for row in info:
        name = row["labels"].get("sql_instance")
        up = reachable.get(name) == 1
        instances.append({
            "instance": name,
            "label": row["labels"].get("label"),
            "environment": row["labels"].get("environment"),
            "reachable": up,
            # Unreachable servers have no current check data: their other checks are paused.
            "overall_severity": SEVERITY.get(int(severity.get(name) or 1), "UNKNOWN") if up else "UNREACHABLE",
            "open_checks": open_counts.get(name, {}) if up else {},
        })
    return {"instances": instances}


async def instance_checks(client, instance: str = "", **_) -> dict:
    """One instance's checks that are not OK, with display names, the worst
    value, and each affected database with its own severity and value."""
    if not instance or len(instance) > 200:
        raise ToolError("instance is required (use a name from fleet_overview)")
    sel = f"{{sql_instance={lit(instance)}}}"
    catalog = {r["labels"]["check"]: r["labels"] for r in await _instant(client, "data_eyes_check_info")}
    severity = await _instant(client, f"data_eyes_health_severity{sel} >= 1")
    values = {r["labels"].get("check"): r["value"] for r in await _instant(client, f"data_eyes_check_value{sel}")}
    db_rows = await _instant(client, f"data_eyes_database_check_severity{sel} >= 2")
    db_values = {(r["labels"].get("check"), r["labels"].get("database")): r["value"]
                 for r in await _instant(client, f"data_eyes_database_check_value{sel}")}
    if not severity and not await _instant(client, f"data_eyes_instance_info{sel}"):
        raise ToolError(f"unknown instance {instance!r}; use a name from fleet_overview")
    databases: Dict[str, list] = {}
    for row in db_rows:
        check, database = row["labels"].get("check"), row["labels"].get("database")
        value = db_values.get((check, database))
        databases.setdefault(check, []).append({
            "database": database, "severity": SEVERITY.get(int(row["value"]), "UNKNOWN"),
            # No number means the severity is fixed by a condition (for example
            # "never checked"), not by a threshold on a value.
            "value": value if value is not None else "no value (fixed severity, e.g. never run)",
        })
    checks = []
    for row in sorted(severity, key=lambda r: -(r["value"] or 0)):
        key = row["labels"].get("category", "").removeprefix("alert.")
        meta = catalog.get(key, {})
        checks.append({"check": key, "name": meta.get("name", key), "group": meta.get("group"), "unit": meta.get("unit") or None,
                       "severity": SEVERITY.get(int(row["value"] or 1), "UNKNOWN"),
                       # Worst number across databases; it does not belong to every affected database.
                       "worst_value": values.get(key),
                       "databases": databases.get(key, [])[:20]})
    return {"instance": instance, "checks_not_ok": checks}


async def query(client, promql: str = "", **_) -> dict:
    """Instant PromQL query (current values)."""
    if not promql or len(promql) > 2000:
        raise ToolError("promql is required (at most 2000 characters)")
    rows = await _instant(client, promql)
    return {"series": rows[:MAX_SERIES], "truncated": len(rows) > MAX_SERIES}


async def query_range(client, promql: str = "", hours: float = 24, **_) -> dict:
    """PromQL over a time range, downsampled to at most MAX_POINTS points."""
    if not promql or len(promql) > 2000:
        raise ToolError("promql is required (at most 2000 characters)")
    hours = min(max(float(hours or 24), 0.25), MAX_RANGE_HOURS)
    end = time.time()
    step = max(60, math.ceil(hours * 3600 / MAX_POINTS))
    data = await _api(client, "query_range", {"query": promql, "start": end - hours * 3600, "end": end, "step": step})
    series = [{"labels": _labels(r["metric"]),
               "points": [[time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t)), _number(v)] for t, v in r["values"]]}
              for r in data["result"]]
    return {"step_seconds": step, "series": series[:MAX_SERIES], "truncated": len(series) > MAX_SERIES}


Tool = Callable[..., Awaitable[dict]]

TOOLS: Dict[str, dict] = {
    "fleet_overview": {
        "fn": fleet_overview,
        "description": "List every monitored SQL Server instance with environment, reachability, overall severity and counts of open checks. Start here.",
        "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "status": "Reading the fleet overview",
    },
    "instance_checks": {
        "fn": instance_checks,
        "description": "Checks that are not OK on one instance (name, group, severity, value and unit, affected databases).",
        "schema": {"type": "object", "properties": {"instance": {"type": "string", "description": "sql_instance name from fleet_overview"}},
                   "required": ["instance"], "additionalProperties": False},
        "status": "Reading the instance's checks",
    },
    "query": {
        "fn": query,
        "description": "Run an instant PromQL query against the Data Eyes metrics (current values).",
        "schema": {"type": "object", "properties": {"promql": {"type": "string"}}, "required": ["promql"], "additionalProperties": False},
        "status": "Querying Prometheus",
    },
    "query_range": {
        "fn": query_range,
        "description": "Run a PromQL query over the last N hours (max 720 = 30 days); returns downsampled points.",
        "schema": {"type": "object", "properties": {"promql": {"type": "string"},
                                                    "hours": {"type": "number", "description": "How far back, in hours (default 24, max 720)"}},
                   "required": ["promql"], "additionalProperties": False},
        "status": "Querying history",
    },
}


async def run_tool(client: httpx.AsyncClient, name: str, arguments: dict) -> str:
    """Run one tool and return JSON text for the model (errors included)."""
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        result = await tool["fn"](client, **(arguments or {}))
    except ToolError as exc:
        result = {"error": str(exc)}
    except httpx.HTTPError as exc:
        result = {"error": f"Prometheus is unreachable ({type(exc).__name__})"}
    except (TypeError, ValueError) as exc:
        result = {"error": f"invalid arguments: {exc}"}
    text = json.dumps(result, default=str)
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + '..." [truncated]'
