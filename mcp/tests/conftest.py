"""Isolate unit tests from operator secrets and the live fleet."""
import os
from pathlib import Path

for key, value in {
    "MCP_ACCESS_FILE": str(Path(__file__).parent / "nonexistent-test-fleet.yaml"),
    "PROMETHEUS_URL": "",
    "DEFAULT_PRINCIPAL": "",
    "DEFAULT_INSTANCE": "",
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
      tools: [list_configured_instances, query_metric]
      instances: [dev]
      objects:  # pre-0.2 object grants are ignored
        - databases: [Sales]
instances:
  - name: dev
    label: Dev
    environment: development
  - name: beta
    label: Beta
    environment: development
  - name: prod
    label: Prod
    environment: production
"""


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """A developer's environment may set these, so pin them per test."""
    monkeypatch.setattr(config.settings, "PROMETHEUS_URL", "http://prometheus:9090")
    monkeypatch.setattr(config.settings, "ALLOWED_HOST", None)


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    path = tmp_path / "instances.yaml"
    path.write_text(FLEET, encoding="utf-8")
    monkeypatch.setattr(config.settings, "MCP_ACCESS_FILE", str(path))
    monkeypatch.setattr(config.settings, "DEPLOYMENT_ENVIRONMENT", "development")
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "alice")
    monkeypatch.setattr(config.settings, "DEFAULT_INSTANCE", None)
    monkeypatch.setattr(config.settings, "RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr(auth, "http_mode", False)
    auth._calls.clear()
    return path
