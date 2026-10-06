from data_eyes_mcp.core import config


def test_shared_fleet_resolves_from_mcp_project_directory(tmp_path, monkeypatch):
    """The core package depth must not change project-relative fleet paths."""
    module = tmp_path / "mcp/src/data_eyes_mcp/core/config.py"
    module.parent.mkdir(parents=True)
    module.touch()
    monkeypatch.setattr(config, "__file__", str(module))
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", "../instances.yaml")
    monkeypatch.chdir(tmp_path.parent)

    assert config.instances_file_path() == tmp_path / "instances.yaml"
