"""Settings and the shared instances.yaml fleet file.

The fleet file holds the SQL Server instances and the `mcp_security` principals
(allowed tools and instances). It is re-read only when its mtime changes.
Object-level access (databases, schemas, tables, columns) is enforced by the
SQL Server login each instance uses, not here.
"""

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# <PREFIX>_MSSQL_USER/_PASSWORD are read with os.getenv, so .env must reach the
# real process environment, not only the Settings model.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    INSTANCES_FILE: str = "../instances.yaml"
    DEFAULT_INSTANCE: Optional[str] = None
    DEFAULT_DATABASE: Optional[str] = None
    DEPLOYMENT_ENVIRONMENT: Optional[str] = None
    INSTANCE_ALLOWLIST: str = ""

    # stdio identity; HTTP callers are identified only by bearer token hash.
    DEFAULT_PRINCIPAL: Optional[str] = None
    HTTP_TOKEN_HASHES: Dict[str, str] = Field(default_factory=dict)
    ALLOWED_HOST: Optional[str] = None
    PROMETHEUS_URL: Optional[str] = None

    MSSQL_APPLICATION_NAME: str = Field(default="Data Eyes MCP", max_length=128)
    MSSQL_CONNECTION_TIMEOUT: int = Field(default=30, ge=1)
    MSSQL_QUERY_TIMEOUT: int = Field(default=30, ge=1)
    MAX_ROWS_PER_QUERY: int = Field(default=50000, ge=1)
    MAX_RESPONSE_BYTES: int = Field(default=2_000_000, ge=1024)
    MAX_CELL_LENGTH: int = Field(default=4000, ge=1)
    MAX_CONCURRENT_QUERIES: int = Field(default=8, ge=1)
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, ge=0)  # tool calls per principal; 0 disables

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"


settings = Settings()


class Instance(BaseModel):
    name: str
    label: str
    mssql_connection_string: str
    environment: Optional[str] = None
    credential_env_prefix: Optional[str] = None


class Principal(BaseModel):
    tools: List[str] = Field(default_factory=list)
    instances: List[str] = Field(default_factory=list)


class Fleet(BaseModel):
    instances: Dict[str, Instance] = Field(default_factory=dict)
    principals: Dict[str, Principal] = Field(default_factory=dict)


_cache: tuple = (None, Fleet())


def fleet_path() -> Path:
    """Resolve INSTANCES_FILE; relative paths are relative to the mcp/ project."""
    path = Path(settings.INSTANCES_FILE).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path.resolve()


def load_fleet() -> Fleet:
    """Return the deployment's instances and principals, cached by file mtime."""
    global _cache
    path = fleet_path()
    try:
        stamp = (path, path.stat().st_mtime_ns, settings.DEPLOYMENT_ENVIRONMENT, settings.INSTANCE_ALLOWLIST)
    except FileNotFoundError:
        return Fleet()
    if _cache[0] == stamp:
        return _cache[1]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    allowlist = {item.strip() for item in settings.INSTANCE_ALLOWLIST.split(",") if item.strip()}
    instances: Dict[str, Instance] = {}
    for item in data.get("instances") or []:
        instance = Instance(**item)
        if settings.DEPLOYMENT_ENVIRONMENT and instance.environment != settings.DEPLOYMENT_ENVIRONMENT:
            continue
        if allowlist and instance.name not in allowlist:
            continue
        if instance.name in instances:
            raise ValueError(f"Duplicate instance name: {instance.name}")
        instances[instance.name] = instance
    principals = (data.get("mcp_security") or {}).get("principals") or {}
    fleet = Fleet(instances=instances, principals=principals)
    _cache = (stamp, fleet)
    return fleet


def resolve_instance(name: Optional[str], visible: Optional[Callable[[str], bool]] = None) -> Instance:
    """Explicit name, else DEFAULT_INSTANCE, else the only instance.

    `visible` limits the choice (and any names in error messages) to instances
    the caller is granted, so errors never reveal the rest of the fleet.
    """
    instances = {key: value for key, value in load_fleet().instances.items() if visible is None or visible(key)}
    available = ", ".join(instances) or "none"
    if name:
        if name not in instances:
            raise ValueError(f"Unknown instance {name!r}; available: {available}")
        return instances[name]
    if settings.DEFAULT_INSTANCE in instances:
        return instances[settings.DEFAULT_INSTANCE]
    if len(instances) == 1:
        return next(iter(instances.values()))
    raise ValueError(f"Pass `instance`; available: {available}")


def credentials(instance: Instance) -> tuple:
    """Return (user, password, trusted) from the instance's credential prefix."""
    prefix = instance.credential_env_prefix
    trusted = os.getenv(f"{prefix}_MSSQL_TRUSTED_CONNECTION", "").lower() in ("1", "true", "yes", "on")
    return os.getenv(f"{prefix}_MSSQL_USER"), os.getenv(f"{prefix}_MSSQL_PASSWORD"), trusted


def validate(transport: str) -> None:
    """Fail startup on a configuration that could not serve requests safely."""
    fleet = load_fleet()
    if not fleet.instances:
        raise ValueError(f"No instances for this deployment in {fleet_path()}")
    if not fleet.principals:
        raise ValueError("instances.yaml needs at least one mcp_security principal")
    if settings.DEFAULT_INSTANCE and settings.DEFAULT_INSTANCE not in fleet.instances:
        raise ValueError(f"DEFAULT_INSTANCE {settings.DEFAULT_INSTANCE!r} is not in this deployment")
    for instance in fleet.instances.values():
        if not instance.credential_env_prefix:
            raise ValueError(f"Instance {instance.name!r} needs credential_env_prefix")
        user, password, trusted = credentials(instance)
        if not trusted and not (user and password):
            prefix = instance.credential_env_prefix
            raise ValueError(f"Set {prefix}_MSSQL_USER and {prefix}_MSSQL_PASSWORD (or {prefix}_MSSQL_TRUSTED_CONNECTION)")
    if transport == "http":
        import re

        hashes = settings.HTTP_TOKEN_HASHES
        if not hashes or not all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values()):
            raise ValueError("HTTP requires HTTP_TOKEN_HASHES mapping principals to SHA-256 token hashes")
        if len(set(hashes.values())) != len(hashes):
            raise ValueError("HTTP bearer tokens must be unique per principal")
        if not set(hashes) <= set(fleet.principals):
            raise ValueError("Each HTTP token principal needs an mcp_security policy")
