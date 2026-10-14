"""
Pure alert evaluation: settings inheritance, thresholds, double check.
"""

from typing import Iterable, Mapping, Optional, Sequence, Tuple

from app.alerts.catalog import AlertDefinition
from app.alerts.models import EffectiveSetting
from app.alerts.models import Finding

RANK = {"OK": 0, "UNKNOWN": 1, "WARNING": 2, "CRITICAL": 3}
MAX_DETAIL_ITEMS = 5


def worst(severities: Iterable[str], default: str = "OK") -> str:
    result = default
    for severity in severities:
        if RANK.get(severity, 0) > RANK.get(result, 0):
            result = severity
    return result


def effective_setting(definition: AlertDefinition, rows: Mapping[Tuple[str, str], dict], instance: str) -> EffectiveSetting:
    """Catalog default, then the fleet-wide row (instance ''), then the
    instance row. Excluded databases accumulate across both rows."""
    values = {
        "enabled": definition.default_enabled,
        "warning": definition.warning,
        "critical": definition.critical,
        "tier": definition.tier,
        "confirm_samples": definition.confirm_samples,
    }
    excluded = set()
    for row in (rows.get((definition.key, "")), rows.get((definition.key, instance)) if instance else None):
        if not row:
            continue
        for column, name in (("enabled", "enabled"), ("warning_threshold", "warning"), ("critical_threshold", "critical"),
                             ("tier", "tier"), ("confirm_samples", "confirm_samples")):
            if row.get(column) is not None:
                values[name] = row[column]
        excluded.update(name.casefold() for name in row.get("excluded_databases") or [])
    return EffectiveSetting(excluded_databases=frozenset(excluded), **values)


def threshold_severity(value: Optional[float], warning: Optional[float], critical: Optional[float], direction: str) -> str:
    if value is None:
        return "OK"
    breached = (lambda limit: value >= limit) if direction == "above" else (lambda limit: value <= limit)
    if critical is not None and breached(critical):
        return "CRITICAL"
    if warning is not None and breached(warning):
        return "WARNING"
    return "OK"


def item_severity(item, definition: AlertDefinition, setting: EffectiveSetting) -> str:
    return worst([threshold_severity(item.value, setting.warning, setting.critical, definition.direction), item.floor or "OK"])


def is_excluded(item, setting: EffectiveSetting) -> bool:
    return bool(item.database) and item.database.casefold() in setting.excluded_databases


def _format_value(value: float, unit: Optional[str]) -> str:
    text = f"{value:,.1f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return f"{text} {unit}" if unit else text


def describe(item, definition: AlertDefinition) -> str:
    parts = [item.subject]
    if item.value is not None and definition.unit:
        parts.append(_format_value(item.value, definition.unit))
    text = ": ".join(parts)
    return f"{text} — {item.detail}" if item.detail else text


def summarize(findings: Sequence[Finding], definition: AlertDefinition, setting: EffectiveSetting) -> Tuple[str, Optional[float], str]:
    """Worst severity, the worst value in the alert's direction, and a short
    detail naming the offending subjects (metadata only, never query text)."""
    scored = [(finding, item_severity(finding, definition, setting)) for finding in findings if not is_excluded(finding, setting)]
    severity = worst(sev for _, sev in scored)
    values = [finding.value for finding, _ in scored if finding.value is not None]
    metric = (max(values) if definition.direction == "above" else min(values)) if values else None
    bad = sorted((pair for pair in scored if pair[1] != "OK"), key=lambda pair: -RANK[pair[1]])
    lines = [f"{sev} {describe(finding, definition)}" for finding, sev in bad[:MAX_DETAIL_ITEMS]]
    if len(bad) > MAX_DETAIL_ITEMS:
        lines.append(f"…and {len(bad) - MAX_DETAIL_ITEMS} more")
    return severity, metric, "\n".join(lines)


def confirm(previous: Optional[dict], observed: str, confirm_samples: int) -> Tuple[str, int]:
    """Double check: a new severity only replaces the confirmed one after it
    has been observed confirm_samples times in a row. Returns (confirmed, streak)."""
    if previous is None:
        return observed, 1
    streak = previous["streak"] + 1 if previous["observed_severity"] == observed else 1
    if observed == previous["severity"] or streak >= confirm_samples:
        return observed, streak
    return previous["severity"], streak
