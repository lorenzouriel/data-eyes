"""Daily DB checklist: one fleet summary per day to the selected channels.

It is a scheduled report, not an alert, so it bypasses rules and goes
straight to the notification outbox (rule_id NULL) at or after the
configured UTC hour.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import app.modules.alerts.repository as alerts_repository
import app.modules.instances.repository as instances_repository
from app.core.config import settings
from app.modules.alerts.catalog import SELF_INSTANCE
from app.modules.alerts.catalog import title
from app.modules.alerts.evaluation import RANK
from app.modules.alerts.evaluation import worst
from app.modules.notifications.models import NotificationEvent

DIGEST_INSTANCE = "Fleet"
DIGEST_CATEGORY = "daily_checklist"


async def build_digest(now: datetime) -> NotificationEvent:
    instances = [instance.name for instance in await instances_repository.list_instances()] + [SELF_INSTANCE]
    states = [state for state in await alerts_repository.list_states() if state["instance_name"] in instances]
    events = await alerts_repository.recent_event_counts(now - timedelta(hours=24))
    by_instance = defaultdict(list)
    for state in states:
        by_instance[state["instance_name"]].append(state)
    event_counts = defaultdict(list)
    for row in events:
        event_counts[row["instance_name"]].append(row)

    lines, clean, severities = [], [], []
    for name in instances:
        open_alerts = sorted((s for s in by_instance[name] if s["severity"] in ("WARNING", "CRITICAL")),
                             key=lambda s: (-RANK[s["severity"]], s["alert_key"]))
        failing = [s for s in by_instance[name] if s["status"] == "error"]
        recent = event_counts[name]
        if not (open_alerts or failing or recent):
            clean.append(name)
            continue
        severities += [s["severity"] for s in open_alerts] + [row["severity"] for row in recent]
        critical = sum(1 for s in open_alerts if s["severity"] == "CRITICAL")
        lines.append(f"{name}: {critical} critical, {len(open_alerts) - critical} warning open")
        for state in open_alerts:
            first = (state["detail"] or "").splitlines()[0] if state["detail"] else ""
            lines.append(f"  {state['severity']} {title(state['alert_key'])}" + (f" — {first}" if first else ""))
        for row in sorted(recent, key=lambda r: (-RANK[r["severity"]], r["alert_key"])):
            lines.append(f"  {row['events']} {title(row['alert_key'])} event(s) in 24h ({row['severity']})")
        if failing:
            lines.append(f"  {len(failing)} check(s) could not run: " + ", ".join(title(s["alert_key"]) for s in failing[:5]))
    header = f"{len(instances) - 1} instance(s) checked; {len([n for n in clean if n != SELF_INSTANCE])} with nothing open."
    return NotificationEvent(kind="digest", instance=DIGEST_INSTANCE, category=DIGEST_CATEGORY, title="Daily DB checklist",
                             old_severity=None, new_severity=worst(severities), detail="\n".join([header, *lines]),
                             dashboard_link=f"{settings.PUBLIC_BASE_URL}/alerts", timestamp=now)


async def send_if_due(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    setting = await alerts_repository.get_digest_setting()
    if not setting["enabled"] or not setting["channel_ids"] or now.hour < setting["hour_utc"]:
        return False
    if setting["last_sent_on"] == now.date() or not await alerts_repository.claim_digest(now.date()):
        return False
    event = await build_digest(now)
    await alerts_repository.enqueue_digest(setting["channel_ids"], event.model_dump_json(), event.instance, event.category)
    return True
