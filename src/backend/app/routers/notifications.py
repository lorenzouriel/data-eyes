"""Admin-only notification management. Never serialize plaintext secrets."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from .. import crypto, repository
from ..auth import require_admin
from ..notifications import REGISTRY
from ..notifications.models import (
    MASK, SECRET_FIELDS, ChannelInput, DeliveryResult, RuleInput, test_event, validate_config,
)


class SafeNotificationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                # FastAPI's default errors include the rejected input, which could
                # be an entire credential-bearing configuration object.
                raise HTTPException(422, "Invalid notification request") from None
            except (repository.RepositoryUnavailable, crypto.DecryptionError):
                raise HTTPException(503, "Notification storage unavailable") from None
        return safe_handler


router = APIRouter(prefix="/api/notifications", tags=["notifications"],
                   dependencies=[Depends(require_admin)], route_class=SafeNotificationRoute)


async def channel_or_404(channel_id, decrypt=False):
    channel = await repository.get_notification_channel(channel_id, decrypt=decrypt)
    if not channel:
        raise HTTPException(404, "Channel not found")
    return channel


def checked_config(kind, config):
    try:
        return validate_config(kind, config)
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid channel configuration; check required fields and destinations") from None


@router.get("/channels")
async def channels():
    return await repository.list_notification_channels()


@router.post("/channels", status_code=201)
async def create_channel(payload: ChannelInput):
    data = payload.model_dump()
    data["config"] = checked_config(payload.type, payload.config)
    return await repository.save_notification_channel(data)


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: int, payload: ChannelInput):
    old = await channel_or_404(channel_id, decrypt=True)
    if payload.type != old["type"]:
        raise HTTPException(422, "Channel type cannot be changed; create another channel")
    config = dict(payload.config)
    for key in SECRET_FIELDS:
        if key in old["config"] and (key not in config or config[key] == MASK):
            config[key] = old["config"][key]
    data = payload.model_dump()
    data["config"] = checked_config(payload.type, config)
    result = await repository.save_notification_channel(data, channel_id)
    if not result:
        raise HTTPException(404, "Channel not found")
    return result


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int):
    if not await repository.delete_notification("channels", channel_id):
        raise HTTPException(404, "Channel not found")


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: int):
    channel = await channel_or_404(channel_id, decrypt=True)
    event = test_event()
    try:
        result = await asyncio.wait_for(REGISTRY[channel["type"]]().test(channel["config"]), timeout=90)
    except Exception:
        result = DeliveryResult(ok=False, message="Test delivery failed")
    await repository.log_notification_test(channel_id, event, result)
    return result


@router.get("/rules")
async def rules():
    return await repository.list_notification_rules()


@router.post("/rules", status_code=201)
async def create_rule(payload: RuleInput):
    await channel_or_404(payload.channel_id)
    return await repository.save_notification_rule(payload.model_dump())


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, payload: RuleInput):
    await channel_or_404(payload.channel_id)
    result = await repository.save_notification_rule(payload.model_dump(), rule_id)
    if not result:
        raise HTTPException(404, "Rule not found")
    return result


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int):
    if not await repository.delete_notification("rules", rule_id):
        raise HTTPException(404, "Rule not found")


@router.get("/logs")
async def logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), channel_id: int | None = None):
    return await repository.list_notification_logs(limit, offset, channel_id)


@router.delete("/logs/{log_id}", status_code=204)
async def delete_log(log_id: int):
    if not await repository.delete_notification("logs", log_id):
        raise HTTPException(404, "Log not found or delivery still pending")
