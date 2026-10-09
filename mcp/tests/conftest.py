"""Isolate unit tests from operator secrets and the live fleet."""
import os
from pathlib import Path

for key, value in {
    "INSTANCES_FILE": str(Path(__file__).parent / "nonexistent-test-fleet.yaml"),
    "HTTP_TOKEN_HASHES": "{}",
    "PROMETHEUS_URL": "",
    "DEFAULT_PRINCIPAL": "",
    "DEFAULT_INSTANCE": "",
    "DEFAULT_DATABASE": "",
    "INSTANCE_ALLOWLIST": "",
    "DEPLOYMENT_ENVIRONMENT": "",
}.items():
    os.environ[key] = value

import pytest  # noqa: E402

from data_eyes_mcp import auth, config  # noqa: E402

FLEET = """
mcp_security:
  principals:
    alice:
      tools: ["*"]
      instances: [dev, beta]
    bob:
      tools: [list_configured_instances, list_tables]
      instances: [dev]
      objects:  # pre-0.2 object grants are ignored
        - databases: [Sales]
instances:
  - name: dev
    label: Dev
    environment: development
    credential_env_prefix: DEV
    mssql_connection_string: 'Driver={ODBC Driver 18 for SQL Server};Server=dev;Database=master;UID=old;PWD=old'
  - name: beta
    label: Beta
    environment: development
    credential_env_prefix: BETA
    mssql_connection_string: 'Driver={ODBC Driver 18 for SQL Server};Server=beta'
  - name: prod
    label: Prod
    environment: production
    credential_env_prefix: PROD
    mssql_connection_string: 'Driver={ODBC Driver 18 for SQL Server};Server=prod'
"""


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """A developer's mcp/.env is merged into dict settings, so pin them per test."""
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {})
    monkeypatch.setattr(config.settings, "PROMETHEUS_URL", None)
    monkeypatch.setattr(config.settings, "DEFAULT_DATABASE", None)
    monkeypatch.setattr(config.settings, "ALLOWED_HOST", None)


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    path = tmp_path / "instances.yaml"
    path.write_text(FLEET, encoding="utf-8")
    monkeypatch.setattr(config.settings, "INSTANCES_FILE", str(path))
    monkeypatch.setattr(config.settings, "DEPLOYMENT_ENVIRONMENT", "development")
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "alice")
    monkeypatch.setattr(config.settings, "DEFAULT_INSTANCE", None)
    monkeypatch.setattr(config.settings, "RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr(auth, "http_mode", False)
    for prefix in ("DEV", "BETA"):
        monkeypatch.setenv(f"{prefix}_MSSQL_USER", f"{prefix.lower()}_reader")
        monkeypatch.setenv(f"{prefix}_MSSQL_PASSWORD", "s3cret;{x}")
    auth._calls.clear()
    return path
