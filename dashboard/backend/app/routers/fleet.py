"""Main Page API — fleet-wide health summary."""

from fastapi import APIRouter, Depends, HTTPException

from .. import repository
from ..auth import require_auth
from ..health_score import FleetHealth, get_fleet_health

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("", response_model=FleetHealth)
async def get_fleet(_: str = Depends(require_auth)):
    try:
        instances = await repository.list_instances()
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    return await get_fleet_health(instances)
