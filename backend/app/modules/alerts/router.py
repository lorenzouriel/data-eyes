"""Alert catalog API: anyone signed in can read; only admins change settings."""

import app.infrastructure.postgres.pool as postgres_pool
import app.modules.alerts.repository as alerts_repository
import app.modules.instances.repository as instances_repository
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.modules.alerts import engine
from app.modules.alerts.catalog import CATALOG
from app.modules.alerts.catalog import CATALOG_BY_KEY
from app.modules.alerts.catalog import SELF_INSTANCE
from app.modules.alerts.catalog import TIER_SECONDS
from app.modules.alerts.evaluation import effective_setting
from app.modules.alerts.evaluation import index_settings
from app.modules.alerts.models import AlertSettingInput
from app.modules.alerts.models import DigestInput
from app.modules.auth.router import require_admin
from app.modules.auth.router import require_auth


class SafeAlertRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, "Invalid alert request") from None
            except postgres_pool.RepositoryUnavailable:
                raise HTTPException(503, "Alert storage unavailable") from None
        return safe_handler


router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(require_auth)], route_class=SafeAlertRoute)


@router.get("/catalog")
async def catalog():
    return {"alerts": [{**asdict(definition), "has_thresholds": definition.has_thresholds} for definition in CATALOG],
            "tiers": TIER_SECONDS, "settings": await alerts_repository.list_settings()}


def _validated(payload: AlertSettingInput) -> dict:
    definition = CATALOG_BY_KEY.get(payload.alert_key)
    if definition is None:
        raise HTTPException(404, "Unknown alert")
    if payload.instance_name and definition.scope != "instance":
        raise HTTPException(422, "This alert has no per-instance settings")
    if (payload.warning_threshold is not None or payload.critical_threshold is not None) and not definition.has_thresholds:
        raise HTTPException(422, "This alert has no thresholds")
    warning, critical = payload.warning_threshold, payload.critical_threshold
    if warning is not None and critical is not None:
        if (definition.direction == "above" and warning > critical) or (definition.direction == "below" and warning < critical):
            raise HTTPException(422, "Warning must come before critical: lower for 'above' alerts, higher for 'below' alerts")
    excluded = None
    if payload.excluded_databases is not None:
        if not definition.per_database:
            raise HTTPException(422, "This alert does not apply per database")
        excluded = sorted({name.strip() for name in payload.excluded_databases if name.strip()})
        if any(len(name) > 128 for name in excluded):
            raise HTTPException(422, "Database names are at most 128 characters")
    return {**payload.model_dump(), "excluded_databases": excluded}


@router.put("/settings")
async def save_setting(payload: AlertSettingInput, _: str = Depends(require_admin)):
    data = _validated(payload)
    if data["instance_name"] and not await instances_repository.get_instance(data["instance_name"]):
        raise HTTPException(404, "Instance not found")
    definition = CATALOG_BY_KEY[data["alert_key"]]
    rows = index_settings(await alerts_repository.list_settings())
    was_enabled = effective_setting(definition, rows, data["instance_name"]).enabled
    saved = await alerts_repository.upsert_setting(data)
    rows[(saved["alert_key"], saved["instance_name"])] = saved
    if was_enabled and not effective_setting(definition, rows, data["instance_name"]).enabled:
        await alerts_repository.reset_alert(definition.key, data["instance_name"] or None)
    engine.forget(definition.key, data["instance_name"] or None)
    return saved


@router.delete("/settings", status_code=204)
async def reset_setting(alert_key: str = Query(max_length=80), instance_name: str = Query("", max_length=200),
                        _: str = Depends(require_admin)):
    if alert_key not in CATALOG_BY_KEY:
        raise HTTPException(404, "Unknown alert")
    if not await alerts_repository.delete_setting(alert_key, instance_name):
        raise HTTPException(404, "No saved setting for this alert and scope")
    engine.forget(alert_key, instance_name or None)


@router.get("/state")
async def state():
    instances = {instance.name for instance in await instances_repository.list_instances()} | {SELF_INSTANCE}
    return [row for row in await alerts_repository.list_states() if row["instance_name"] in instances]


@router.get("/events")
async def events(limit: int = Query(100, ge=1, le=500), instance_name: str | None = Query(None, max_length=200)):
    return await alerts_repository.list_events(limit, instance_name)


@router.get("/digest", dependencies=[Depends(require_admin)])
async def digest_setting():
    return await alerts_repository.get_digest_setting()


@router.put("/digest", dependencies=[Depends(require_admin)])
async def save_digest(payload: DigestInput):
    known = set(await alerts_repository.channel_ids())
    if set(payload.channel_ids) - known:
        raise HTTPException(422, "Unknown notification channel")
    return await alerts_repository.save_digest_setting(payload.enabled, payload.hour_utc, sorted(set(payload.channel_ids)))
