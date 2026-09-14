import json

import pytest

from data_eyes_mcp import config
from data_eyes_mcp.db import ConnectionError, build_connection_string, request_credentials
from data_eyes_mcp.tools import list_configured_instances


def _write_fleet(path, duplicate: bool = False) -> None:
    second_name = "alpha" if duplicate else "beta"
    path.write_text(
        "instances:\n"
        "  - name: alpha\n"
        "    label: Alpha\n"
        "    environment: production\n"
        "    mssql_connection_string: 'Driver={ODBC Driver 17 for SQL Server};Server=alpha;Database=master'\n"
        f"  - name: {second_name}\n"
        "    label: Beta\n"
        "    environment: staging\n"
        "    mssql_connection_string: 'Driver={ODBC Driver 17 for SQL Server};Server=beta;Database=master'\n",
        encoding="utf-8",
    )


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    path = tmp_path / "instances.yaml"
    _write_fleet(path)
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", str(path))
    monkeypatch.setattr(config.settings, "DEFAULT_INSTANCE", None)
    monkeypatch.setattr(config.settings, "MSSQL_CONNECTION_STRING", None)
    monkeypatch.setattr(config.settings, "MSSQL_USER", None)
    monkeypatch.setattr(config.settings, "MSSQL_PASSWORD", None)
    monkeypatch.setattr(config.settings, "MSSQL_TRUSTED_CONNECTION", None)
    monkeypatch.setattr(config.settings, "DEFAULT_DATABASE", None)
    return path


@pytest.mark.asyncio
async def test_list_configured_instances_never_returns_connection_strings(fleet):
    result = json.loads(await list_configured_instances())

    assert [item["name"] for item in result] == ["alpha", "beta"]
    assert all("mssql_connection_string" not in item for item in result)


def test_each_tool_call_can_select_an_instance(fleet):
    with request_credentials(instance="beta"):
        connection_string = build_connection_string()

    assert "Server=beta" in connection_string
    with pytest.raises(ConnectionError, match="Select an instance"):
        build_connection_string()


def test_duplicate_instance_names_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "instances.yaml"
    _write_fleet(path, duplicate=True)
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", str(path))

    with pytest.raises(ValueError, match="Duplicate instance name"):
        config.load_instances()
