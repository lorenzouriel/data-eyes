import pytest

from app.core import config


@pytest.mark.parametrize("relative_path", ["../instances.yaml", "instances.yaml"])
def test_shared_fleet_resolves_from_backend_directory(tmp_path, monkeypatch, relative_path):
    """Moving settings into core must not move the shared fleet lookup base."""
    module = tmp_path / "backend/app/core/config.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (tmp_path / "instances.yaml").write_text(
        "instances:\n"
        "  - name: synthetic\n"
        "    label: Synthetic fleet\n"
        "    mssql_connection_string: synthetic-not-a-real-connection\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "__file__", str(module))
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", relative_path)
    monkeypatch.chdir(tmp_path.parent)

    assert [instance.name for instance in config.load_seed_instances()] == ["synthetic"]
