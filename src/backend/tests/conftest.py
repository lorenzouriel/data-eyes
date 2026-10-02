"""Tests never load operator credentials or contact the configured fleet."""
import os
import base64

for key, value in {
    "DASHBOARD_ADMIN_PASSWORD": "synthetic-bootstrap-password",
    "SESSION_SECRET_KEY": "synthetic-session-key-at-least-32-characters",
    "INSTANCE_SECRET_KEY": base64.urlsafe_b64encode(b"0" * 32).decode(),
    "REPOSITORY_DSN": "postgresql://unused:unused@127.0.0.1:1/unused",
    "INSTANCES_FILE": "tests/nonexistent-test-fleet.yaml",
    "ANTHROPIC_API_KEY": "",
    "OPENAI_API_KEY": "",
    "LOCAL_AI_API_KEY": "",
}.items():
    os.environ[key] = value
