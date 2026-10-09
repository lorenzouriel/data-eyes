"""Collector settings. Fleet and check settings are deployment-owned YAML."""
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    INSTANCES_FILE: str = "../instances.yaml"
    CHECK_SETTINGS_FILE: str = "checks.yaml"
    STATE_FILE: str = "state/checkpoints.json"
    COLLECTOR_INTERVAL_SECONDS: int = Field(default=30, ge=5)
    # Also the number of instances whose fast cycle runs at once: each cycle
    # issues its queries one at a time, so a running cycle always has a slot.
    SQL_MAX_CONCURRENT_QUERIES: int = Field(default=8, ge=1, le=32)
    SQL_MAX_BACKGROUND_QUERIES: int = Field(default=2, ge=1, le=16)
    SQL_QUEUE_TIMEOUT_SECONDS: float = 5
    SQL_BACKGROUND_QUEUE_TIMEOUT_SECONDS: float = Field(default=60, gt=0)
    SQL_MAX_RESPONSE_BYTES: int = 2_000_000
    SQL_MAX_CELL_LENGTH: int = 100_000
    SQL_APPLICATION_NAME: str = Field(default="Data Eyes Collector", max_length=128)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)


settings = Settings()


class InstanceConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    name: str = Field(min_length=1, max_length=200)
    label: str = ""
    environment: str = ""
    mssql_connection_string: str = Field(repr=False, min_length=1)

    @field_validator("label", "environment", mode="before")
    @classmethod
    def normalize_optional_metadata(cls, value):
        return value or ""


def load_instances():
    data = yaml.safe_load(Path(settings.INSTANCES_FILE).read_text(encoding="utf-8")) or {}
    instances = [InstanceConfig(**item) for item in data.get("instances", [])]
    if not instances or len({i.name for i in instances}) != len(instances):
        raise ValueError("Fleet must contain unique, nonempty instances")
    return instances


def load_check_settings():
    path = Path(settings.CHECK_SETTINGS_FILE)
    rows = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("checks", []) if path.exists() else []
    from app.alerts.models import AlertSettingInput
    from app.alerts.catalog import CATALOG_BY_KEY
    result = {}
    for row in rows:
        parsed = AlertSettingInput(**row).model_dump()
        if parsed["alert_key"] not in CATALOG_BY_KEY:
            raise ValueError("Unknown alert key")
        warning, critical = parsed["warning_threshold"], parsed["critical_threshold"]
        definition = CATALOG_BY_KEY[parsed["alert_key"]]
        if warning is not None and critical is not None:
            valid = warning < critical if definition.direction == "above" else warning > critical
            if not valid:
                raise ValueError("Warning threshold must precede critical threshold")
        result[(parsed["alert_key"], parsed["instance_name"])] = parsed
    return result
