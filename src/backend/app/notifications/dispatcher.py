"""Transition-only planning and independent, durable channel deliveries."""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .. import repository
from ..config import settings
from . import REGISTRY
from .models import DeliveryResult, NotificationEvent

logger = logging.getLogger(__name__)
RANK = {"UNKNOWN": -1, "OK": 0, "WARNING": 1, "CRITICAL": 2}


def in_quiet_hours(rule, now):
    start, end = rule.get("quiet_start"), rule.get("quiet_end")
    if start is None or end is None:
        return False
    hour = now.astimezone(timezone.utc).hour
    return start <= hour < end if start < end else hour >= start or hour < end


def plan(snapshots, states, rules, previous, now):
    states = {(s["instance_name"], s["category"]): s for s in states}
    last = {(p["rule_id"], p["instance_name"], p["category"]): p["last_sent"] for p in previous}
    groups = defaultdict(list)
    for snapshot in snapshots:
        instance, category, severity = snapshot["instance_name"], snapshot["category"], snapshot["severity"]
        old = states.get((instance, category))
        if severity not in RANK or (old and (old["severity"] == severity or old["captured_at"] >= snapshot["captured_at"])):
            continue
        # The first sample establishes a baseline, avoiding a fleet-wide alert storm.
        if old is None:
            continue
        event = NotificationEvent(instance=instance, category=category, old_severity=old["severity"],
                                  new_severity=severity, metric_value=snapshot["metric_value"],
                                  timestamp=snapshot["captured_at"],
                                  dashboard_link=f"{settings.PUBLIC_BASE_URL}/instances/{quote(instance, safe='')}")
        for rule in rules:
            if not rule["enabled"] or (rule.get("instance") and rule["instance"] != instance) or (rule.get("category") and rule["category"] != category):
                continue
            recovery = severity == "OK" and old["severity"] in ("WARNING", "CRITICAL")
            if recovery:
                matches = rule.get("recovery", False)
            else:
                matches = severity in rule["severities"]
            if not matches:
                continue
            key = "*" if rule.get("group_by_instance") else category
            groups[(rule["id"], instance, key)].append((rule, event))
    result = []
    for (rule_id, instance, category), pairs in groups.items():
        rule = pairs[0][0]
        events = [pair[1] for pair in pairs]
        event = max(events, key=lambda e: RANK[e.new_severity])
        if rule.get("group_by_instance"):
            event = event.model_copy(update={"category": "*", "grouped": events, "metric_value": None})
        cooldown = rule.get("cooldown_seconds")
        if cooldown is None:
            cooldown = settings.NOTIFICATION_COOLDOWN_SECONDS
        last_sent = last.get((rule_id, instance, category))
        reason = "Quiet hours (UTC)" if in_quiet_hours(rule, now) else ""
        if not reason and last_sent and (now - last_sent).total_seconds() < cooldown:
            reason = "Cooldown"
        result.append((rule, event, reason))
    return result


async def _deliver(row):
    try:
        channel = await repository.get_notification_channel(row["channel_id"], decrypt=True) if row["channel_id"] else None
        if not channel or not channel["enabled"]:
            result = DeliveryResult(ok=False, message="Channel disabled or deleted")
        elif row["attempts"] > 3:
            result = DeliveryResult(ok=False, message="Delivery lease expired; retry limit reached")
        else:
            event = NotificationEvent.model_validate_json(row["event"])
            result = await asyncio.wait_for(REGISTRY[channel["type"]]().send(event, channel["config"]), timeout=90)
    except Exception:
        # Exceptions can contain passwords, webhook URLs or provider response bodies.
        result = DeliveryResult(ok=False, message="Delivery failed")
    try:
        await repository.finish_notification(row, result)
    except repository.RepositoryUnavailable:
        logger.warning("Notification result could not be saved; delivery lease will expire")


async def evaluate(since=None):
    since = since or datetime.now(timezone.utc) - timedelta(seconds=max(300, settings.COLLECTOR_INTERVAL_SECONDS * 5))
    await repository.enqueue_notifications(plan, since)
    # Bounded concurrent deliveries keep a slow provider independent of the
    # others. Unsent records stay in the durable outbox for the next cycle.
    rows = []
    for _ in range(40):
        row = await repository.claim_notification()
        if row is None:
            break
        rows.append(row)
    await asyncio.gather(*(_deliver(row) for row in rows))
