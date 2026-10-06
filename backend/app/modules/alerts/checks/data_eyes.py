"""Alerts about Data Eyes itself, recorded under the SELF_INSTANCE pseudo-instance."""

from datetime import timedelta

import app.modules.alerts.repository as alerts_repository
from app.modules.alerts.checks.registry import check
from app.modules.alerts.models import Finding


@check("notification_delivery_failing")
async def notification_delivery_failing(ctx):
    rows = await alerts_repository.channel_failures(ctx.now - timedelta(hours=1))
    return [Finding(row["name"], float(row["failed"]), detail="failed deliveries in the last hour") for row in rows]
