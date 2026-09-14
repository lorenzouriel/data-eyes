"""
Insights API — the embedded real-time agent's HTTP surface.

- GET  /api/insights/feed: the background-sweep-generated insight history.
- GET  /api/insights/fleet/stream (SSE): on-page-load commentary for the Main Page.
- GET  /api/insights/instances/{name}/tabs/{tab}/stream (SSE): same, per instance drill-down tab.
- POST /api/insights/explain (SSE): on-demand deep explanation — the one path
  using the stronger model, gated behind explicit user action.
- POST /api/insights/instances/{name}/advisor: structured, on-demand advisor
  report over real diagnostic data (see insights_agent.generate_advisor_report).
- POST /api/insights/instances/{name}/advisor/dismiss: persist a dismissed finding.
- POST /api/insights/ask (SSE): multi-turn "Ask the fleet" chat.

Every endpoint degrades to "no insight" rather than an error when
ANTHROPIC_API_KEY isn't configured — this feature is additive, never a
dependency for the rest of the dashboard to function.
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import diagnostics, insights_agent, insights_feed, repository
from ..auth import require_auth
from ..config import InstanceConfig
from ..health_score import get_fleet_health
from ..mssql_client import MSSQLError
from .instance_tabs import TAB_BUILDERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/insights", tags=["insights"])


async def _find_instance(instance_name: str) -> InstanceConfig:
    try:
        instance = await repository.get_instance(instance_name)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return instance


async def _safe(coro: Awaitable[Any]) -> Optional[Any]:
    try:
        return await coro
    except (MSSQLError, repository.RepositoryUnavailable) as e:
        logger.warning("Advisor context call failed: %s", e)
        return None


async def _sse(text_iter: AsyncIterator[str]):
    async for chunk in text_iter:
        if chunk:
            yield f"data: {json.dumps({'text': chunk})}\n\n"
    yield "event: done\ndata: {}\n\n"


@router.get("/feed")
async def get_feed(_: str = Depends(require_auth)):
    return {"insights": insights_feed.get_feed()}


@router.get("/fleet/stream")
async def stream_fleet_insight(_: str = Depends(require_auth)):
    try:
        instances = await repository.list_instances()
    except repository.RepositoryUnavailable:
        instances = []
    fleet = await get_fleet_health(instances)
    context = {"fleet": [i.model_dump() for i in fleet.instances]}
    return StreamingResponse(_sse(insights_agent.stream_insight(context)), media_type="text/event-stream")


@router.get("/instances/{instance_name}/tabs/{tab_name}/stream")
async def stream_tab_insight(
    instance_name: str, tab_name: str, database: Optional[str] = None, _: str = Depends(require_auth)
):
    builder = TAB_BUILDERS.get(tab_name)
    if not builder:
        raise HTTPException(status_code=404, detail=f"Unknown tab: {tab_name}")
    instance = await _find_instance(instance_name)
    tab_data = await builder(instance.mssql_connection_string, instance_name, database)
    context = {key: result["data"] for key, result in tab_data.items() if result.get("data")}
    return StreamingResponse(_sse(insights_agent.stream_insight(context)), media_type="text/event-stream")


class ExplainRequest(BaseModel):
    instance_name: str
    tab_name: Optional[str] = None
    database: Optional[str] = None
    question: Optional[str] = None


@router.post("/explain")
async def explain(payload: ExplainRequest, _: str = Depends(require_auth)):
    instance = await _find_instance(payload.instance_name)
    context: dict = {}

    if payload.tab_name:
        builder = TAB_BUILDERS.get(payload.tab_name)
        if not builder:
            raise HTTPException(status_code=404, detail=f"Unknown tab: {payload.tab_name}")
        tab_data = await builder(instance.mssql_connection_string, payload.instance_name, payload.database)
        context = {key: result["data"] for key, result in tab_data.items() if result.get("data")}
    else:
        try:
            score = await diagnostics.fleet_health_score(instance.mssql_connection_string)
            context = {"fleet_health_score": score}
        except MSSQLError as e:
            logger.warning("Explain: instance %s unreachable: %s", payload.instance_name, e)

    return StreamingResponse(
        _sse(insights_agent.stream_deep_explanation(context, payload.question)),
        media_type="text/event-stream",
    )


@router.post("/instances/{instance_name}/advisor")
async def generate_advisor(instance_name: str, database: Optional[str] = None, _: str = Depends(require_auth)):
    instance = await _find_instance(instance_name)
    conn_str = instance.mssql_connection_string

    wait_history, blocking, top_queries, missing_idx = await asyncio.gather(
        _safe(repository.get_wait_category_history(instance_name)),
        _safe(diagnostics.blocking_snapshot(conn_str)),
        _safe(diagnostics.top_queries(conn_str, database=database, top_n=5)),
        _safe(diagnostics.missing_indexes(conn_str, database=database, top_n=10)),
    )

    plan = None
    if top_queries:
        plan_handle = top_queries[0].get("PlanHandle")
        if plan_handle:
            plan = await _safe(diagnostics.query_plan(conn_str, plan_handle))

    context = {
        "wait_category_history": wait_history,
        "blocking": blocking,
        "top_queries": top_queries,
        "top_query_plan": plan,
        "missing_indexes": missing_idx,
    }

    report = await insights_agent.generate_advisor_report(instance_name, context)
    if report is None:
        raise HTTPException(
            status_code=503,
            detail="Advisor is unavailable right now (no ANTHROPIC_API_KEY configured, or the model call failed).",
        )

    dismissed = await _safe(repository.get_dismissed_advisor_findings(instance_name)) or set()
    findings = [f for f in report.findings if f.finding_key not in dismissed]
    return {"summary": report.summary, "findings": [f.model_dump() for f in findings]}


class DismissRequest(BaseModel):
    finding_key: str


@router.post("/instances/{instance_name}/advisor/dismiss")
async def dismiss_advisor_finding(instance_name: str, payload: DismissRequest, _: str = Depends(require_auth)):
    try:
        await repository.dismiss_advisor_finding(instance_name, payload.finding_key)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True}


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/ask")
async def ask_fleet(payload: AskRequest, _: str = Depends(require_auth)):
    try:
        instances = await repository.list_instances()
    except repository.RepositoryUnavailable:
        instances = []
    fleet = await get_fleet_health(instances)
    context = {"fleet": [i.model_dump() for i in fleet.instances]}
    history = [{"role": m.role, "content": m.content} for m in payload.messages]
    return StreamingResponse(_sse(insights_agent.stream_chat(history, context)), media_type="text/event-stream")
