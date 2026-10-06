from pathlib import Path

import pytest
import yaml

from app.modules.alerts.catalog import CATALOG
from app.modules.alerts.catalog import CATALOG_BY_KEY
from app.modules.alerts.catalog import TIER_SECONDS
from app.modules.alerts.checks import CHECKS

THRESHOLDS = Path(__file__).resolve().parents[4] / ".claude/knowledge-base/_static/thresholds.yaml"


def test_every_alert_has_exactly_one_check_and_unique_key():
    assert len(CATALOG_BY_KEY) == len(CATALOG)
    assert set(CHECKS) == set(CATALOG_BY_KEY)


def test_agreed_alert_list_changes():
    names = {definition.name for definition in CATALOG}
    # Removed, or merged into another alert.
    for gone in ("DB Without Backup", "Traces Size", "Blocked Long Process", "Large LDF File", "Log Full",
                 "Int-Bigint Limit", "Double Check Alert", "Alert Without Clear", "Daily DB CheckList",
                 "New Ignored DB", "Database Created", "Update Statistics"):
        assert gone not in names
    for kept in ("Blocked Process", "Transaction Log Health", "Identity Values / Int-Bigint Limit", "New Database Not Covered",
                 "Stale Statistics", "SQL Agent Stopped", "AG Failover", "Notification Channel Failing"):
        assert kept in names
    assert not CATALOG_BY_KEY["index_fragmentation"].default_enabled


@pytest.mark.parametrize("definition", CATALOG, ids=lambda d: d.key)
def test_definitions_are_consistent(definition):
    assert definition.tier in TIER_SECONDS
    assert 1 <= definition.confirm_samples <= 10
    if definition.warning is not None and definition.critical is not None:
        if definition.direction == "above":
            assert definition.warning <= definition.critical
        else:
            assert definition.warning >= definition.critical
    if definition.has_thresholds:
        assert definition.unit


@pytest.mark.skipif(not THRESHOLDS.exists(), reason="knowledge base not present (e.g. backend-only image)")
def test_defaults_match_threshold_registry():
    registry = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))["alerts"]
    expected = {d.key: {"unit": d.unit, "direction": d.direction, "warning": d.warning, "critical": d.critical}
                for d in CATALOG if d.has_thresholds}
    assert registry == expected
