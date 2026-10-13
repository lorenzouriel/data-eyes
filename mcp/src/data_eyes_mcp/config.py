"""
Credential-free monitoring access policy; SQL credentials belong to the collector.
"""
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process settings from the environment (Compose or .mcp.json); defaults otherwise."""
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    MCP_ACCESS_FILE: str = "../mcp-access.yaml"
    DEFAULT_INSTANCE: Optional[str] = None
    DEPLOYMENT_ENVIRONMENT: Optional[str] = None
    INSTANCE_ALLOWLIST: str = ""

    # stdio identity; HTTP callers are identified only by their token_sha256.
    DEFAULT_PRINCIPAL: Optional[str] = None
    ALLOWED_HOST: Optional[str] = None
    # Service name other containers use to reach this server (e.g. the agent
    # calling http://data-eyes-mcp-dev:8080/mcp); accepted as a Host in addition
    # to ALLOWED_HOST. Set per service by docker-compose.yml.
    INTERNAL_HOST: Optional[str] = None
    PROMETHEUS_URL: Optional[str] = None

    MAX_RESPONSE_BYTES: int = Field(default=2_000_000, ge=1024)
    MAX_CONCURRENT_QUERIES: int = Field(default=8, ge=1)
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, ge=0)  # tool calls per principal; 0 disables

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"


settings = Settings()


class Instance(BaseModel):
    name: str
    label: str
    model_config = SettingsConfigDict(extra="forbid", hide_input_in_errors=True)
    environment: Optional[str] = None


class Principal(BaseModel):
    tools: List[str] = Field(default_factory=list)
    instances: List[str] = Field(default_factory=list)
    # SHA-256 hex digest of this principal's HTTP bearer token (never the token).
    token_sha256: Optional[str] = Field(default=None, repr=False)


class Fleet(BaseModel):
    instances: Dict[str, Instance] = Field(default_factory=dict)
    principals: Dict[str, Principal] = Field(default_factory=dict)


_cache: tuple = (None, Fleet())


def fleet_path() -> Path:
    """Resolve MCP_ACCESS_FILE; relative paths are relative to the mcp/ project."""
    path = Path(settings.MCP_ACCESS_FILE).expanduser()
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


def token_hashes() -> Dict[str, str]:
    """Principal name -> token_sha256, for principals that have a token."""
    return {name: p.token_sha256 for name, p in load_fleet().principals.items() if p.token_sha256}


def validate(transport: str) -> None:
    """Fail startup on a configuration that could not serve requests safely."""
    fleet = load_fleet()
    if not fleet.instances:
        raise ValueError(f"No instances for this deployment in {fleet_path()}")
    if not fleet.principals:
        raise ValueError("mcp-access.yaml needs at least one mcp_security principal")
    if settings.DEFAULT_INSTANCE and settings.DEFAULT_INSTANCE not in fleet.instances:
        raise ValueError(f"DEFAULT_INSTANCE {settings.DEFAULT_INSTANCE!r} is not in this deployment")
    if not settings.PROMETHEUS_URL:
        raise ValueError("PROMETHEUS_URL is required")
    if transport == "http":
        hashes = token_hashes()
        if not hashes:
            raise ValueError("HTTP requires token_sha256 on at least one mcp_security principal")
        if not all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values()):
            raise ValueError("token_sha256 must be a SHA-256 hex digest (64 lowercase hex characters)")
        if len(set(hashes.values())) != len(hashes):
            raise ValueError("HTTP bearer tokens must be unique per principal")
