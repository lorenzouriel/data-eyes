import app.modules.monitoring.diagnostics.common as diagnostics_common
import app.modules.monitoring.diagnostics.fleet as diagnostics_fleet
import asyncio

from app.infrastructure.sqlserver.client import MSSQLError


def test_unknown_is_not_hidden_by_healthy_rows():
    assert diagnostics_common._worst_severity([{"severity": "OK"}, {"severity": "UNKNOWN"}]) == "UNKNOWN"
    assert diagnostics_common._worst_severity([{"severity": "UNKNOWN"}, {"severity": "CRITICAL"}]) == "CRITICAL"


def test_failed_check_is_not_reported_as_healthy(monkeypatch):
    async def query(connection, sql):
        if "CommandLog" in sql:
            raise MSSQLError("History unavailable")
        return []
    monkeypatch.setattr(diagnostics_fleet, "_query", query)
    result = asyncio.run(diagnostics_fleet.fleet_health_score("synthetic"))
    assert result["overall_severity"] == "UNKNOWN"
    assert result["categories"]["checkdb_health"] == "UNKNOWN"
    assert result["categories"]["backup_health"] == "OK"
