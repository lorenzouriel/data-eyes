from datetime import datetime, timedelta, timezone

import pytest

from app.modules.alerts import evaluation
from app.modules.alerts.catalog import CATALOG_BY_KEY
from app.modules.alerts.models import Finding
from app.modules.alerts.models import Occurrence

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
DISK = CATALOG_BY_KEY["disk_space"]  # below: warning 20, critical 5
LOG = CATALOG_BY_KEY["transaction_log_health"]  # above: warning 75, critical 90, per database


def setting(definition, **rows):
    return evaluation.effective_setting(definition, evaluation.index_settings(rows.get("rows", [])), rows.get("instance", ""))


def row(key, instance="", **values):
    base = {"alert_key": key, "instance_name": instance, "enabled": None, "warning_threshold": None,
            "critical_threshold": None, "tier": None, "confirm_samples": None, "excluded_databases": None}
    return {**base, **values}


def test_settings_inherit_catalog_then_fleet_then_instance():
    rows = [row("disk_space", enabled=False, warning_threshold=50, excluded_databases=["Dev"]),
            row("disk_space", "prod", enabled=True, critical_threshold=10, tier="fast", excluded_databases=["Scratch"])]
    fleet = setting(DISK, rows=rows)
    assert (fleet.enabled, fleet.warning, fleet.critical, fleet.tier) == (False, 50, 5, "standard")
    prod = setting(DISK, rows=rows, instance="prod")
    assert (prod.enabled, prod.warning, prod.critical, prod.tier) == (True, 50, 10, "fast")
    assert prod.excluded_databases == {"dev", "scratch"}
    other = setting(DISK, rows=rows, instance="other")
    assert other.enabled is False and other.excluded_databases == {"dev"}


@pytest.mark.parametrize("value,direction,expected", [
    (None, "above", "OK"), (74, "above", "OK"), (75, "above", "WARNING"), (90, "above", "CRITICAL"),
    (21, "below", "OK"), (20, "below", "WARNING"), (5, "below", "CRITICAL"),
])
def test_threshold_direction(value, direction, expected):
    warning, critical = (75, 90) if direction == "above" else (20, 5)
    assert evaluation.threshold_severity(value, warning, critical, direction) == expected


def test_summary_uses_floor_exclusions_and_worst_value():
    findings = [Finding("Sales", 95, database="Sales", detail="reuse wait LOG_BACKUP"),
                Finding("Dev", 99, database="DEV"),
                Finding("Big", 10, database="Big", detail="log larger than data", floor="WARNING"),
                Finding("Fine", 20, database="Fine")]
    severity, metric, detail = evaluation.summarize(findings, LOG, setting(LOG, rows=[row(LOG.key, excluded_databases=["dev"])]))
    assert severity == "CRITICAL" and metric == 95
    assert detail.splitlines() == ["CRITICAL Sales: 95 % — reuse wait LOG_BACKUP", "WARNING Big: 10 % — log larger than data"]
    assert "Dev" not in detail and "Fine" not in detail


def test_summary_below_direction_reports_minimum():
    severity, metric, _ = evaluation.summarize([Finding("C:\\", 50), Finding("E:\\", 3.5)], DISK, setting(DISK))
    assert severity == "CRITICAL" and metric == 3.5


def test_summary_caps_detail():
    _, _, detail = evaluation.summarize([Finding(f"db{i}", 99, database=f"db{i}") for i in range(8)], LOG, setting(LOG))
    assert len(detail.splitlines()) == 6 and detail.endswith("…and 3 more")


def test_double_check_requires_consecutive_samples():
    state = None
    history = []
    for observed in ["OK", "CRITICAL", "OK", "CRITICAL", "CRITICAL", "CRITICAL", "OK"]:
        confirmed, streak = evaluation.confirm(state, observed, 2)
        state = {"severity": confirmed, "observed_severity": observed, "streak": streak}
        history.append(confirmed)
    assert history == ["OK", "OK", "OK", "OK", "CRITICAL", "CRITICAL", "CRITICAL"]
    assert evaluation.confirm({"severity": "OK", "observed_severity": "OK", "streak": 4}, "WARNING", 1) == ("WARNING", 1)


def test_tiers_are_due_on_schedule():
    assert evaluation.is_due(None, "daily", NOW, 60)
    assert evaluation.is_due(NOW - timedelta(seconds=55), "fast", NOW, 60)
    assert not evaluation.is_due(NOW - timedelta(seconds=30), "fast", NOW, 60)
    assert not evaluation.is_due(NOW - timedelta(minutes=4), "standard", NOW, 60)
    assert evaluation.is_due(NOW - timedelta(minutes=5), "standard", NOW, 60)
    assert not evaluation.is_due(NOW - timedelta(hours=23), "daily", NOW, 60)


def test_event_rows_drop_ok_and_excluded():
    definition = CATALOG_BY_KEY["slow_file_growth"]  # above: 1000 / 10000 ms
    occurrences = [Occurrence("a", NOW, "Sales log", 500, database="Sales"),
                   Occurrence("b", NOW, "Sales log", 12000, database="Sales", detail="log file grew 512 MB"),
                   Occurrence("c", NOW, "Dev log", 12000, database="Dev")]
    rows = evaluation.event_rows(occurrences, definition, setting(definition, rows=[row(definition.key, excluded_databases=["Dev"])]))
    assert [(r["dedup_key"], r["severity"]) for r in rows] == [("b", "CRITICAL")]
    assert rows[0]["detail"] == "Sales log: 12,000 ms — log file grew 512 MB"
