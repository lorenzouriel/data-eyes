"""
Backend liveness — distinct from SQL Server fleet health (that's
GET /api/fleet). Unauthenticated: container orchestrators and Docker
healthchecks need to reach this without a session cookie.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/health/collector")
def collector_health():
    """For an external uptime monitor: 503 when the collector (and with it
    every alert) has not completed a cycle recently. Kept separate from
    /api/health so a slow SQL Server never restarts the container."""
    from app.modules.monitoring import collector
    now = datetime.now(timezone.utc)
    limit = max(5 * settings.COLLECTOR_INTERVAL_SECONDS, 300)
    last = collector.last_cycle_completed_at
    reference = last or collector.started_at
    stale = reference is None or (now - reference).total_seconds() > limit
    body = {"status": "stale" if stale else "ok" if last else "starting",
            "last_cycle_completed_at": last.isoformat() if last else None}
    return JSONResponse(body, status_code=503 if stale else 200)
