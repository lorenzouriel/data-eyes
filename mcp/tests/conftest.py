"""Isolate unit tests from operator secrets and the live fleet."""
import os
from pathlib import Path

for key, value in {
    "INSTANCES_FILE": str(Path(__file__).parent / "nonexistent-test-fleet.yaml"),
    "MCP_TRANSPORT": "stdio",
    "HTTP_TOKEN_HASHES": "{}",
    "REPOSITORY_DSN": "",
    "MSSQL_CONNECTION_STRING": "",
    "DEFAULT_PRINCIPAL": "",
    "DEFAULT_INSTANCE": "",
    "DEFAULT_DATABASE": "",
    "INSTANCE_ALLOWLIST": "",
    "DEPLOYMENT_ENVIRONMENT": "",
}.items():
    os.environ[key] = value
