"""Main Page API — fleet-wide health summary."""

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..config import load_instances
from ..health_score import FleetHealth, get_fleet_health

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("", response_model=FleetHealth)
async def get_fleet(_: str = Depends(require_auth)):
    instances = load_instances()
    return await get_fleet_health(instances)
