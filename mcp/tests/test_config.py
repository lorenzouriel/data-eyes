import os

import pytest

from data_eyes_mcp import config


def test_fleet_is_filtered_to_the_deployment(fleet):
    assert list(config.load_fleet().instances) == ["dev", "beta"]


def test_old_object_grants_are_ignored(fleet):
    assert config.load_fleet().principals["bob"].instances == ["dev"]


def test_fleet_reloads_when_the_file_changes(fleet):
    assert "beta" in config.load_fleet().instances
    fleet.write_text(fleet.read_text().replace("name: beta", "name: gamma"))
    stat = fleet.stat()
    os.utime(fleet, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert "gamma" in config.load_fleet().instances


def test_duplicate_instance_names_are_rejected(fleet):
    fleet.write_text(fleet.read_text().replace("name: beta", "name: dev"))
    with pytest.raises(ValueError, match="Duplicate"):
        config.load_fleet()


def test_instance_must_be_selected_when_ambiguous(fleet):
    assert config.resolve_instance("beta").name == "beta"
    with pytest.raises(ValueError, match="Pass `instance`"):
        config.resolve_instance(None)
    with pytest.raises(ValueError, match="Unknown instance 'prod'"):
        config.resolve_instance("prod")


def _rewrite(fleet, old, new):
    fleet.write_text(fleet.read_text().replace(old, new))
    stat = fleet.stat()
    os.utime(fleet, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


def test_sql_credentials_are_rejected(fleet):
    config.validate("stdio")
    _rewrite(fleet, "    label: Beta", "    label: Beta\n    mssql_connection_string: forbidden")
    with pytest.raises(ValueError):
        config.load_fleet()


def test_prometheus_is_required(fleet, monkeypatch):
    monkeypatch.setattr(config.settings, "PROMETHEUS_URL", "")
    with pytest.raises(ValueError, match="PROMETHEUS_URL"):
        config.validate("stdio")


def test_validate_requires_principal_token_hashes_for_http(fleet):
    with pytest.raises(ValueError, match="token_sha256"):
        config.validate("http")
    _rewrite(fleet, "    alice:\n", "    alice:\n      token_sha256: not-a-hash\n")
    with pytest.raises(ValueError, match="hex digest"):
        config.validate("http")
    _rewrite(fleet, "token_sha256: not-a-hash", "token_sha256: " + "a" * 64)
    config.validate("http")
    assert config.token_hashes() == {"alice": "a" * 64}


def test_relative_fleet_path_is_relative_to_the_mcp_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "MCP_ACCESS_FILE", "../mcp-access.yaml")
    monkeypatch.chdir(tmp_path)
    assert config.fleet_path() == config.Path(config.__file__).resolve().parents[3] / "mcp-access.yaml"
