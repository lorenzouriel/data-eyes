"""
Configuration for the Data Eyes dashboard backend.

Loads runtime settings from environment variables (.env) and the fleet
registry from instances.yaml — the dashboard's equivalent of Grafana's
datasources.yml (monitor/grafana/datasources.yml), except each entry here
points at a data-eyes-mcp server rather than a direct SQL connection (see
mcp/docker-compose.fleet.yml for the matching per-instance MCP topology).
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Session / auth — see app/auth.py for why this is a single shared
    # credential rather than a user database.
    DASHBOARD_ADMIN_USERNAME: str = "admin"
    DASHBOARD_ADMIN_PASSWORD: str
    SESSION_SECRET_KEY: str
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 12  # 12h

    # Fleet registry (relative to this backend's project root unless absolute)
    INSTANCES_FILE: str = "instances.yaml"

    # MCP client
    MCP_CALL_TIMEOUT_SECONDS: float = 15.0

    # CORS — only needed when the frontend runs on a different origin (e.g.
    # the Vite dev server on :5173 during local development). JSON array
    # string, e.g. ["http://localhost:5173"]. Empty = same-origin only.
    CORS_ALLOW_ORIGINS: List[str] = []

    # Trend-history repository (app/repository.py, app/collector.py) — a
    # dedicated database, never a monitored SQL Server. Optional: if unset,
    # the collector simply never starts and the dashboard runs exactly as it
    # did in Phase 2/3 (current-state views only, no trend strips).
    REPOSITORY_DSN: Optional[str] = None
    COLLECTOR_INTERVAL_SECONDS: int = 60
    TREND_RETENTION_DAYS: int = 30

    # Embedded insights agent (app/insights_agent.py, app/insights_sweep.py) —
    # optional: if unset, every insight endpoint degrades to "no insight"
    # rather than erroring, and the background sweep never starts. Model
    # tiering matches the approved plan: a fast/cheap model for routine
    # commentary, a stronger model only for on-demand deep explanations.
    ANTHROPIC_API_KEY: Optional[str] = None
    INSIGHTS_SWEEP_INTERVAL_SECONDS: int = 600  # 10 min (plan's 5-15 min range)
    INSIGHTS_FEED_MAX_SIZE: int = 50

    HOST: str = "0.0.0.0"
    PORT: int = 8090

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()


class InstanceConfig(BaseModel):
    """One monitored SQL Server instance, backed by its own data-eyes-mcp server."""

    name: str
    label: str
    mcp_url: str
    environment: Optional[str] = None


def load_instances() -> List[InstanceConfig]:
    """Load the fleet registry from instances.yaml. Missing file -> empty fleet
    (not an error) so the Main Page can still render a "no instances configured"
    state rather than crashing."""
    path = Path(settings.INSTANCES_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / settings.INSTANCES_FILE
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [InstanceConfig(**item) for item in data.get("instances", [])]
