"""
Top-N historical activity API — the DPA-style Top Waits / Programs /
Databases / Machines / DB Users / Files / Drives / Plans / SQL Statements /
Blocking Statements / Deadlocks charts, plus the Specific-Day query
drill-down. Same graceful-degrade-to-empty philosophy as routers/trends.py:
a repository outage or missing data returns an empty result, never a 500 —
these are history views, not part of the live monitoring path.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_auth
from ..repository import DIMENSION_NAMES, RepositoryUnavailable, get_dimension_log, get_top_dimension_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances/{instance_name}/top", tags=["activity"])


def _validate_dimension(dimension: str) -> None:
    if dimension not in DIMENSION_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown dimension: {dimension}")


@router.get("/{dimension}")
async def get_top_dimension(
    instance_name: str,
    dimension: str,
    range: str = Query(default="30d", pattern="^(30d|7d)$"),
    limit: int = Query(default=10, ge=1, le=25),
    _: str = Depends(require_auth),
):
    _validate_dimension(dimension)
    since_days = 7 if range == "7d" else 30
    try:
        result = await get_top_dimension_history(instance_name, dimension, since_days, limit)
    except RepositoryUnavailable:
        return {"series": [], "other": [], "available": False}
    except Exception:
        logger.exception("Unexpected error fetching top-%s for %s", dimension, instance_name)
        return {"series": [], "other": [], "available": False}
    return {**result, "available": True}


@router.get("/{dimension}/log")
async def get_dimension_log_route(
    instance_name: str,
    dimension: str,
    day: date = Query(...),
    _: str = Depends(require_auth),
):
    _validate_dimension(dimension)
    try:
        rows = await get_dimension_log(instance_name, dimension, day.isoformat())
    except RepositoryUnavailable:
        return {"rows": [], "available": False}
    except Exception:
        logger.exception("Unexpected error fetching %s log for %s on %s", dimension, instance_name, day)
        return {"rows": [], "available": False}
    return {"rows": rows, "available": True}
