import asyncio

from app import diagnostics
from app.mssql_client import MSSQLError


def test_unknown_is_not_hidden_by_healthy_rows():
    assert diagnostics._worst_severity([{"severity": "OK"}, {"severity": "UNKNOWN"}]) == "UNKNOWN"
    assert diagnostics._worst_severity([{"severity": "UNKNOWN"}, {"severity": "CRITICAL"}]) == "CRITICAL"


def test_failed_check_is_not_reported_as_healthy(monkeypatch):
    async def query(connection, sql):
        if "CommandLog" in sql:
            raise MSSQLError("History unavailable")
        return []
    monkeypatch.setattr(diagnostics, "_query", query)
    result = asyncio.run(diagnostics.fleet_health_score("synthetic"))
    assert result["overall_severity"] == "UNKNOWN"
    assert result["categories"]["checkdb_health"] == "UNKNOWN"
