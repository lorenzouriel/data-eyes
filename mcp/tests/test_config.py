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


def test_validate_requires_scoped_credentials(fleet, monkeypatch):
    config.validate("stdio")
    monkeypatch.delenv("BETA_MSSQL_PASSWORD")
    with pytest.raises(ValueError, match="BETA_MSSQL_PASSWORD"):
        config.validate("stdio")


def test_validate_requires_hashed_tokens_for_known_principals(fleet, monkeypatch):
    with pytest.raises(ValueError, match="HTTP_TOKEN_HASHES"):
        config.validate("http")
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {"mallory": "a" * 64})
    with pytest.raises(ValueError, match="policy"):
        config.validate("http")
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {"alice": "a" * 64})
    config.validate("http")


def test_relative_fleet_path_is_relative_to_the_mcp_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", "../instances.yaml")
    monkeypatch.chdir(tmp_path)
    assert config.fleet_path() == config.Path(config.__file__).resolve().parents[3] / "instances.yaml"
