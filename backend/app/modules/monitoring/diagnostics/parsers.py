"""Parsers implementation."""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple
from app.modules.monitoring.diagnostics.health import _SHOWPLAN_NS
import logging
logger = logging.getLogger(__name__)


def _find_relops(elem, depth: int = 0) -> List[Tuple[Any, int]]:
    """Yield every <RelOp> in document order with its nesting depth, walking
    into each RelOp's operator-specific child (<Hash>, <NestedLoops>, ...) to
    find the RelOps it contains one level deeper."""
    out: List[Tuple[Any, int]] = []
    for child in elem:
        if child.tag == f"{_SHOWPLAN_NS}RelOp":
            out.append((child, depth))
            out.extend(_find_relops(child, depth + 1))
        else:
            out.extend(_find_relops(child, depth))
    return out


def _direct_child_relops(elem) -> List[Any]:
    out = []
    for child in elem:
        if child.tag == f"{_SHOWPLAN_NS}RelOp":
            out.append(child)
        else:
            out.extend(c for c in child if c.tag == f"{_SHOWPLAN_NS}RelOp")
    return out


def _subtree_cost(elem) -> float:
    try:
        return float(elem.get("EstimatedTotalSubtreeCost", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_plan_xml(xml_text: str, avg_elapsed_ms: float) -> List[Dict[str, Any]]:
    """Parse SQL Server's ShowPlan XML into a flat, depth-ordered operator
    list with each node's own (non-subtree) share of the plan's total
    estimated cost, used to allocate the query's real average elapsed time
    proportionally across operators.

    This is cost-based attribution — the same technique SSMS's estimated
    plan view uses, applied to the actual cached plan for this statement.
    It is NOT independently measured per-operator runtime: SQL Server only
    exposes that via Query Store's actual-execution statistics or live
    Extended Events tracing, neither of which this reads. The `estimated_
    time_ms` field name is deliberate — never rename it to imply it was
    measured.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("query_plan: could not parse plan XML")
        return []

    relops = _find_relops(root)
    if not relops:
        return []

    total_cost = _subtree_cost(relops[0][0]) or 1.0  # first RelOp in document order is the plan root

    nodes = []
    for elem, depth in relops:
        own_cost = _subtree_cost(elem) - sum(_subtree_cost(c) for c in _direct_child_relops(elem))
        own_cost = max(own_cost, 0.0)
        share = (own_cost / total_cost) if total_cost else 0.0
        nodes.append(
            {
                "depth": depth,
                "physical_op": elem.get("PhysicalOp", "?"),
                "logical_op": elem.get("LogicalOp", "?"),
                "estimated_rows": elem.get("EstimateRows"),
                "cost_share": round(share, 4),
                "estimated_time_ms": round(share * avg_elapsed_ms, 2),
            }
        )
    return nodes


def _parse_deadlock_events(xml_text: str) -> List[Dict[str, Any]]:
    """Shreds the system_health Extended Events ring buffer's XML for
    xml_deadlock_report events — same xml.etree.ElementTree technique
    _parse_plan_xml() uses for query plans, applied to a different schema (a
    deadlock graph's <process>/<resource-list>, not <RelOp>). Best-effort:
    SQL Server's deadlock XML shape has minor version-to-version variance, so
    every field read here degrades to None rather than raising if a
    particular attribute is absent."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("deadlock_events: could not parse system_health ring buffer XML")
        return []

    events: List[Dict[str, Any]] = []
    for event in root.findall(".//event[@name='xml_deadlock_report']"):
        deadlock = event.find(".//deadlock")
        if deadlock is None:
            continue

        processes = {p.get("id"): p for p in deadlock.findall("./process-list/process")}
        victim_ids = [v.get("id") for v in deadlock.findall("./victim-list/victimProcess")]
        victim = processes.get(victim_ids[0]) if victim_ids else None

        resource_parts = []
        for res in deadlock.findall("./resource-list/*"):
            label = res.get("objectname") or res.get("associatedObjectId") or res.get("waitresource")
            resource_parts.append(f"{res.tag}{': ' + label if label else ''}")

        victim_login = victim.get("loginname") if victim is not None else None
        victim_host = victim.get("hostname") if victim is not None else None
        events.append(
            {
                "occurred_at": event.get("timestamp"),
                "database_name": victim.get("currentdbname") if victim is not None else None,
                "victim_login": victim_login,
                "victim_host": victim_host,
                "victim_program": victim.get("clientapp") if victim is not None else None,
                "resource_description": "; ".join(resource_parts) or None,
                "process_count": len(processes),
                "summary": f"{len(processes)} process(es) — victim {victim_login or 'unknown'}@{victim_host or 'unknown'}",
            }
        )
    return events
