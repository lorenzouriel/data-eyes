"""Main Page API — fleet-wide health summary."""

import app.infrastructure.postgres.pool as postgres_pool
import app.modules.instances.repository as instances_repository

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.router import require_auth
from app.modules.monitoring.health_score import FleetHealth
from app.modules.monitoring.health_score import get_fleet_health

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("", response_model=FleetHealth)
async def get_fleet(_: str = Depends(require_auth)):
    try:
        instances = await instances_repository.list_instances()
    except postgres_pool.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    return await get_fleet_health(instances)
