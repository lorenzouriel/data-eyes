"""Transition-only planning and independent, durable channel deliveries."""

import app.infrastructure.postgres.pool as postgres_pool
import app.modules.notifications.repository as notifications_repository
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from app.core.config import settings
from app.modules.alerts.catalog import SELF_INSTANCE
from app.modules.notifications import REGISTRY
from app.modules.notifications.models import DeliveryResult
from app.modules.notifications.models import NotificationEvent

logger = logging.getLogger(__name__)
RANK = {"UNKNOWN": -1, "OK": 0, "WARNING": 1, "CRITICAL": 2}


def in_quiet_hours(rule, now):
    start, end = rule.get("quiet_start"), rule.get("quiet_end")
    if start is None or end is None:
        return False
    hour = now.astimezone(timezone.utc).hour
    return start <= hour < end if start < end else hour >= start or hour < end


def dashboard_link(instance):
    if instance == SELF_INSTANCE:
        return f"{settings.PUBLIC_BASE_URL}/alerts"
    return f"{settings.PUBLIC_BASE_URL}/instances/{quote(instance, safe='')}"


def _matches(rule, instance, category):
    return rule["enabled"] and not (rule.get("instance") and rule["instance"] != instance) \
        and not (rule.get("category") and rule["category"] != category)


def _group_key(rule, category):
    return "*" if rule.get("group_by_instance") else category


def plan(snapshots, states, rules, previous, now, events=()):
    """Decide deliveries for state transitions, still-open reminders and
    escalations, and one-off events. Returns (rule, event, suppression reason)."""
    states = {(s["instance_name"], s["category"]): s for s in states}
    last = {(p["rule_id"], p["instance_name"], p["category"]): p["last_sent"] for p in previous}
    groups = defaultdict(list)
    for snapshot in snapshots:
        instance, category, severity = snapshot["instance_name"], snapshot["category"], snapshot["severity"]
        old = states.get((instance, category))
        # The first sample establishes a baseline, avoiding a fleet-wide alert storm.
        if severity not in RANK or old is None or old["captured_at"] >= snapshot["captured_at"]:
            continue
        transition = old["severity"] != severity
        old_since = old.get("changed_at") or old["captured_at"]
        opened = snapshot["captured_at"] if transition else old_since
        base = {"instance": instance, "category": category, "title": snapshot.get("title"), "detail": snapshot.get("detail"),
                "metric_value": snapshot["metric_value"], "timestamp": snapshot["captured_at"], "dashboard_link": dashboard_link(instance)}
        for rule in rules:
            if not _matches(rule, instance, category):
                continue
            escalate = rule.get("escalate_after_seconds")
            sent = last.get((rule["id"], instance, _group_key(rule, category)))
            if transition:
                if severity == "OK" and old["severity"] in ("WARNING", "CRITICAL"):
                    # An escalation rule only reports recovery of an incident it escalated.
                    if not rule.get("recovery") or (escalate and not (sent and sent >= old_since)):
                        continue
                elif severity not in rule["severities"] or escalate:
                    continue
                groups[(rule["id"], instance, _group_key(rule, category))].append(
                    (rule, NotificationEvent(**base, old_severity=old["severity"], new_severity=severity)))
            elif severity in ("WARNING", "CRITICAL") and severity in rule["severities"]:
                current = sent if sent and sent >= opened else None
                renotify = rule.get("renotify_seconds")
                if escalate and current is None:
                    due = (now - opened).total_seconds() >= escalate
                else:
                    due = bool(renotify) and (now - (current or opened)).total_seconds() >= renotify
                if due:
                    groups[(rule["id"], instance, _group_key(rule, category))].append(
                        (rule, NotificationEvent(**base, kind="reminder", old_severity=severity, new_severity=severity, open_since=opened)))
    for occurrence in events:
        instance, category, severity = occurrence["instance_name"], occurrence["category"], occurrence["severity"]
        for rule in rules:
            # Events never stay open, so they have nothing to escalate.
            if not _matches(rule, instance, category) or severity not in rule["severities"] or rule.get("escalate_after_seconds"):
                continue
            groups[(rule["id"], instance, _group_key(rule, category))].append((rule, NotificationEvent(
                kind="event", instance=instance, category=category, title=occurrence.get("title"), detail=occurrence.get("detail"),
                old_severity=None, new_severity=severity, metric_value=occurrence.get("metric_value"),
                timestamp=occurrence["occurred_at"], dashboard_link=dashboard_link(instance))))
    result = []
    for (rule_id, instance, category), pairs in groups.items():
        rule = pairs[0][0]
        batch = [pair[1] for pair in pairs]
        event = max(batch, key=lambda e: RANK[e.new_severity])
        if rule.get("group_by_instance"):
            event = event.model_copy(update={"category": "*", "title": None, "detail": None, "grouped": batch, "metric_value": None})
        elif len(batch) > 1:
            # Several occurrences of one event alert in a cycle become one message.
            event = event.model_copy(update={"grouped": batch, "metric_value": None, "detail": None})
        cooldown = rule.get("cooldown_seconds")
        if cooldown is None:
            cooldown = settings.NOTIFICATION_COOLDOWN_SECONDS
        last_sent = last.get((rule_id, instance, category))
        reason = "Quiet hours (UTC)" if in_quiet_hours(rule, now) else ""
        if not reason and last_sent and (now - last_sent).total_seconds() < cooldown:
            reason = "Cooldown"
        if reason and all(e.kind == "reminder" for e in batch):
            continue  # A deferred reminder stays due; logging it every cycle would flood the log.
        result.append((rule, event, reason))
    return result


async def _deliver(row):
    try:
        channel = await notifications_repository.get_notification_channel(row["channel_id"], decrypt=True) if row["channel_id"] else None
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
        await notifications_repository.finish_notification(row, result)
    except postgres_pool.RepositoryUnavailable:
        logger.warning("Notification result could not be saved; delivery lease will expire")


async def evaluate(since=None):
    since = since or datetime.now(timezone.utc) - timedelta(seconds=max(300, settings.COLLECTOR_INTERVAL_SECONDS * 5))
    await notifications_repository.enqueue_notifications(plan, since)
    # Bounded concurrent deliveries keep a slow provider independent of the
    # others. Unsent records stay in the durable outbox for the next cycle.
    rows = []
    for _ in range(40):
        row = await notifications_repository.claim_notification()
        if row is None:
            break
        rows.append(row)
    await asyncio.gather(*(_deliver(row) for row in rows))
