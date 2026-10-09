import json
from unittest.mock import AsyncMock

import pytest

from data_eyes_mcp import config, db, output, tools


@pytest.fixture
def captured(fleet, monkeypatch):
    """Record every statement instead of connecting."""
    calls = []

    async def run(instance, sql, params=(), database=None, max_rows=None):
        calls.append({"instance": instance, "sql": sql, "params": list(params), "database": database})
        return db.Result(["severity"], [("OK",)])

    monkeypatch.setattr(db, "run", run)
    return calls


@pytest.mark.parametrize("name, parts", [
    ("t", ["t"]),
    ("dbo.t", ["dbo", "t"]),
    ("[My DB].dbo.[a.b]", ["My DB", "dbo", "a.b"]),
    ('"x""y".[z]]w]', ['x"y', "z]w"]),
])
def test_split_name(name, parts):
    assert tools.split_name(name) == parts


@pytest.mark.parametrize("name", ["", "a..b", "a.", "a.b.c.d", "[open"])
def test_split_name_rejects_bad_names(name):
    with pytest.raises(ValueError):
        tools.split_name(name)


async def test_sample_table_queries_exactly_the_named_object(captured):
    await tools.sample_table(table="[Sales].hr.[pay;roll]", limit=500, instance="dev")
    assert captured[0]["sql"] == "SELECT TOP (100) * FROM [hr].[pay;roll]"
    assert captured[0]["database"] == "Sales"


async def test_discovery_filters_are_bound_parameters(captured):
    await tools.list_tables(schema="x' OR 1=1 --", instance="dev")
    assert "x'" not in captured[0]["sql"] and captured[0]["params"] == [200, "x' OR 1=1 --"]


async def test_db_space_filter_applies_and_connects_to_that_database(captured):
    await tools.db_space(database="O'Brien", instance="dev")
    assert "d.name = N'O''Brien'" in captured[0]["sql"] and captured[0]["database"] == "O'Brien"


async def test_tools_deny_ungranted_instances(captured, monkeypatch):
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "bob")
    assert (await tools.list_tables(instance="beta")).startswith("ERROR:")
    assert (await tools.sample_table(table="t", instance="dev")).startswith("ERROR:")
    assert captured == []


async def test_fleet_score_ranks_unknown_above_ok(fleet, monkeypatch):
    async def run(instance, sql, *args, **kwargs):
        if "backupset" in sql:
            raise db.DatabaseError("permission denied")
        return db.Result(["severity"], [("OK",)])

    monkeypatch.setattr(db, "run", run)
    result = json.loads(await tools.fleet_health_score(instance="dev"))
    assert result["categories"]["backup_health"] == "UNKNOWN"
    assert result["overall_severity"] == "UNKNOWN"


def test_json_output_obeys_the_byte_cap(monkeypatch):
    monkeypatch.setattr(config.settings, "MAX_RESPONSE_BYTES", 1024)
    rendered = output.as_json(["note"], [("x" * 600,), ("y" * 600,)])
    data = json.loads(rendered)
    assert len(rendered.encode()) <= 1024 and data["_meta"]["truncated"] and len(data["rows"]) == 1
    assert data["_meta"]["trust"] == "untrusted_database_content"


def test_promql_label_values_are_escaped():
    value = 'dev"} or up{job="x'
    assert tools._selector(value, "overall") == "data_eyes_overall_severity{sql_instance=" + json.dumps(value) + "}"


async def test_history_never_queries_outside_the_deployment(fleet, monkeypatch):
    query = AsyncMock()
    monkeypatch.setattr(tools, "_prometheus", query)
    assert (await tools.get_latest_snapshot(instance="prod")).startswith("ERROR:")
    query.assert_not_called()


async def test_history_lookback_is_bounded(fleet, monkeypatch):
    query = AsyncMock(return_value=[{"values": [[100, "2"]]}])
    monkeypatch.setattr(tools, "_prometheus", query)
    result = json.loads(await tools.get_severity_trend(instance="dev", hours=100000))
    start, end, step = query.call_args.args[1:]
    assert round(end - start) == 720 * 3600 and step >= 1296
    assert result["rows"][0]["severity"] == "WARNING"


async def test_errors_never_reveal_ungranted_instances(captured, monkeypatch):
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "bob")  # granted only dev
    result = await tools.list_tables(instance="nope")
    assert "available: dev" in result and "beta" not in result
    # bob's only granted instance becomes his default
    await tools.list_tables()
    assert captured[-1]["instance"] == "dev"


async def test_principal_without_the_tool_learns_nothing_about_instances(captured, monkeypatch):
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "bob")
    result = await tools.db_space(instance="nope")
    assert "may not use 'db_space'" in result and "dev" not in result and captured == []


async def test_unidentified_callers_are_audited(fleet, monkeypatch, caplog):
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", None)
    with caplog.at_level("WARNING", logger="data_eyes_mcp.audit"):
        assert (await tools.list_configured_instances()).startswith("ERROR:")
    assert '"reason": "unauthenticated"' in caplog.text
