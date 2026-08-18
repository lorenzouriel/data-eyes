"""
Configuration for the Data Eyes dashboard backend.

Loads runtime settings from environment variables (.env). The instance
registry itself now lives in the database (app/repository.py's instance_*
functions) — instances.yaml is only a one-time seed read at startup, not the
live source of truth; see load_seed_instances() below and
app/repository.py's seed_instances_from_yaml().
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Session / auth bootstrap — see app/auth.py. DASHBOARD_ADMIN_USERNAME/
    # PASSWORD only matter once, to seed the first admin account when the
    # user table is empty; after that, accounts are managed through the UI.
    DASHBOARD_ADMIN_USERNAME: str = "admin"
    DASHBOARD_ADMIN_PASSWORD: str
    SESSION_SECRET_KEY: str
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 12  # 12h

    # Fleet registry seed (relative to this backend's project root unless
    # absolute) — read once at startup, see load_seed_instances() below.
    INSTANCES_FILE: str = "instances.yaml"

    # Encrypts instance connection strings at rest (app/crypto.py). Generate
    # with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    INSTANCE_SECRET_KEY: str

    # CORS — only needed when the frontend runs on a different origin (e.g.
    # the Vite dev server on :5173 during local development). JSON array
    # string, e.g. ["http://localhost:5173"]. Empty = same-origin only.
    CORS_ALLOW_ORIGINS: List[str] = []

    # The dashboard's own Postgres database (app/repository.py) — trend
    # history, the instance registry, and user accounts all live here. No
    # longer optional: unlike Phase 4's trend-history-only role, the
    # instance registry and login are core functionality now, not a
    # nice-to-have. A monitored SQL Server is never stored here — this is
    # strictly the dashboard's own store, separate from every system it watches.
    REPOSITORY_DSN: str
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
    """One monitored SQL Server instance, reached by direct connection."""

    name: str
    label: str
    mssql_connection_string: str
    environment: Optional[str] = None


def load_seed_instances() -> List[InstanceConfig]:
    """Read instances.yaml as a one-time seed list — used only by
    app/repository.py's seed_instances_from_yaml() at startup, never by a
    request-serving code path. Missing file -> no seed entries (not an
    error); a fresh instance table with no seed file is a valid, empty
    starting state, same as it always could be."""
    path = Path(settings.INSTANCES_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / settings.INSTANCES_FILE
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [InstanceConfig(**item) for item in data.get("instances", [])]
