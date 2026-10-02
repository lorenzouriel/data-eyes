"""
Configuration for the Data Eyes dashboard backend.

Loads runtime settings from environment variables (.env). The instance
The shared src/instances.yaml fleet is synchronized into the database-backed
registry at startup and is also consumed directly by MCP.
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Session / auth bootstrap — see app/auth.py. DASHBOARD_ADMIN_USERNAME/
    # PASSWORD only matter once, to seed the first admin account when the
    # user table is empty; after that, accounts are managed through the UI.
    DASHBOARD_ADMIN_USERNAME: str = "admin"
    DASHBOARD_ADMIN_PASSWORD: str = Field(min_length=12, max_length=72)
    SESSION_SECRET_KEY: str = Field(min_length=32)
    SESSION_HTTPS_ONLY: bool = True
    # The backend is only reachable through the frontend nginx, which sets
    # X-Real-IP to the real client address. Disable if exposing it directly.
    TRUST_X_REAL_IP: bool = True
    SQL_ALLOWED_SERVERS: List[str] = []
    SQL_MAX_CONCURRENT_QUERIES: int = Field(default=8, ge=1, le=64)
    SQL_MAX_BACKGROUND_QUERIES: int = Field(default=4, ge=1, le=64)
    SQL_QUEUE_TIMEOUT_SECONDS: float = Field(default=5.0, ge=0.1, le=60)
    SQL_MAX_RESPONSE_BYTES: int = Field(default=2_000_000, ge=1024)
    SQL_MAX_CELL_LENGTH: int = Field(default=100_000, ge=256)
    AI_MAX_CONCURRENT_REQUESTS: int = Field(default=2, ge=1, le=16)
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 12  # 12h

    # Fleet registry seed (relative to this backend's project root unless
    # absolute) — read once at startup, see load_seed_instances() below.
    # Shared fleet file used by both the dashboard and src/mcp.
    INSTANCES_FILE: str = "../instances.yaml"

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
    # activity_sample is written every few seconds per instance, so it keeps a
    # much shorter window than the minute-cadence trend tables.
    ACTIVITY_RETENTION_DAYS: int = Field(default=7, ge=1)
    # Activity sampling (app/collector.py's _run_activity_sampler_forever)
    # runs on its own, much tighter loop than COLLECTOR_INTERVAL_SECONDS —
    # catching a session actually mid-query/mid-wait needs a sampling
    # interval close to query duration, not the other collector jobs'
    # cumulative-counter cadence. Higher write volume to activity_sample is
    # the accepted tradeoff (see repository/init.sql's comment on the table).
    ACTIVITY_SAMPLE_INTERVAL_SECONDS: int = 3

    # Provider-neutral AI for Ask, Advisor, explanations, and insight sweeps.
    # Supported providers: anthropic, openai ("chatgpt" alias), and local.
    AI_PROVIDER: str = "anthropic"
    AI_ROUTINE_MODEL: Optional[str] = None
    AI_DEEP_MODEL: Optional[str] = None
    AI_REQUEST_TIMEOUT_SECONDS: float = 120.0

    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LOCAL_AI_BASE_URL: str = "http://host.docker.internal:11434/v1"
    LOCAL_AI_API_KEY: Optional[str] = None
    INSIGHTS_SWEEP_INTERVAL_SECONDS: int = 600  # 10 min (plan's 5-15 min range)
    INSIGHTS_FEED_MAX_SIZE: int = 50

    HOST: str = "0.0.0.0"
    PORT: int = 8090

    @field_validator("DASHBOARD_ADMIN_PASSWORD")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt silently/loudly rejects >72 *bytes*; max_length counts characters.
        if len(value.encode()) > 72:
            raise ValueError("must be at most 72 UTF-8 bytes")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()


class InstanceConfig(BaseModel):
    """One monitored SQL Server instance, reached by direct connection."""

    name: str
    label: str
    mssql_connection_string: str
    environment: Optional[str] = None


def load_seed_instances() -> List[InstanceConfig]:
    """Read the shared fleet file for synchronization at application startup."""
    path = Path(settings.INSTANCES_FILE)
    if not path.is_absolute():
        backend_root = Path(__file__).resolve().parent.parent
        path = backend_root / settings.INSTANCES_FILE
        # Compatibility with pre-move .env files that still say
        # INSTANCES_FILE=instances.yaml. The canonical file now lives one
        # level above backend/, at src/instances.yaml.
        if not path.exists():
            shared_path = backend_root.parent / Path(settings.INSTANCES_FILE).name
            if shared_path.exists():
                path = shared_path
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    instances = [InstanceConfig(**item) for item in data.get("instances", [])]
    names = [instance.name for instance in instances]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Duplicate instance name(s): {', '.join(duplicates)}")
    return instances
