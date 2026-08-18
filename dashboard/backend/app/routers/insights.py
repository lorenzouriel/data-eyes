"""
Insights API — the embedded real-time agent's HTTP surface.

- GET  /api/insights/feed: the background-sweep-generated insight history.
- GET  /api/insights/fleet/stream (SSE): on-page-load commentary for the Main Page.
- GET  /api/insights/instances/{name}/databases/{db}/tabs/{tab}/stream (SSE): same, per drill-down tab.
- POST /api/insights/explain (SSE): on-demand deep explanation — the one path
  using the stronger model, gated behind explicit user action.

Every endpoint degrades to "no insight" rather than an error when
ANTHROPIC_API_KEY isn't configured — this feature is additive, never a
dependency for the rest of the dashboard to function.
"""

import json
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import diagnostics, insights_agent, insights_feed, repository
from ..auth import require_auth
from ..config import InstanceConfig
from ..health_score import get_fleet_health
from ..mssql_client import MSSQLError
from .databases import TAB_BUILDERS

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


@router.get("/instances/{instance_name}/databases/{database_name}/tabs/{tab_name}/stream")
async def stream_tab_insight(
    instance_name: str, database_name: str, tab_name: str, _: str = Depends(require_auth)
):
    builder = TAB_BUILDERS.get(tab_name)
    if not builder:
        raise HTTPException(status_code=404, detail=f"Unknown tab: {tab_name}")
    instance = await _find_instance(instance_name)
    tab_data = await builder(instance.mssql_connection_string, database_name)
    context = {key: result["data"] for key, result in tab_data.items() if result.get("data")}
    return StreamingResponse(_sse(insights_agent.stream_insight(context)), media_type="text/event-stream")


class ExplainRequest(BaseModel):
    instance_name: str
    database_name: Optional[str] = None
    tab_name: Optional[str] = None
    question: Optional[str] = None


@router.post("/explain")
async def explain(payload: ExplainRequest, _: str = Depends(require_auth)):
    context: dict = {}

    if payload.database_name and payload.tab_name:
        builder = TAB_BUILDERS.get(payload.tab_name)
        if not builder:
            raise HTTPException(status_code=404, detail=f"Unknown tab: {payload.tab_name}")
        instance = await _find_instance(payload.instance_name)
        tab_data = await builder(instance.mssql_connection_string, payload.database_name)
        context = {key: result["data"] for key, result in tab_data.items() if result.get("data")}
    else:
        instance = await _find_instance(payload.instance_name)
        try:
            score = await diagnostics.fleet_health_score(instance.mssql_connection_string)
            context = {"fleet_health_score": score}
        except MSSQLError as e:
            logger.warning("Explain: instance %s unreachable: %s", payload.instance_name, e)

    return StreamingResponse(
        _sse(insights_agent.stream_deep_explanation(context, payload.question)),
        media_type="text/event-stream",
    )
