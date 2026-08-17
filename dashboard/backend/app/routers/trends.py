"""Trend-history API — powers the TrendStrip components on the Main Page
and the per-database drill-down tabs. Returns an empty series (not an
error) when the repository isn't configured or simply doesn't have data
yet — a fresh deployment needs a few collection cycles before any trend
exists, and that's an expected state, not a failure."""

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import require_auth
from ..repository import RepositoryUnavailable, get_trend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances/{instance_name}/trend", tags=["trends"])


@router.get("/{category}")
async def get_instance_trend(
    instance_name: str,
    category: str,
    hours: int = Query(default=24, ge=1, le=24 * 30),
    _: str = Depends(require_auth),
):
    try:
        points = await get_trend(instance_name, category, since_hours=hours)
    except RepositoryUnavailable:
        return {"points": [], "available": False}
    except Exception:
        # Belt-and-suspenders: repository.py normalizes its own failures to
        # RepositoryUnavailable, but a trend chart is a nice-to-have — it
        # must never 500 the page it's embedded in over an unexpected error.
        logger.exception("Unexpected error fetching trend for %s/%s", instance_name, category)
        return {"points": [], "available": False}
    return {"points": points, "available": True}
