"""Check results, the per-cycle check context, and API input models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["fast", "standard", "slow", "daily"]


@dataclass(frozen=True)
class Finding:
    """One measured subject of a state alert (a drive, a database, a session).

    value is compared with the alert's thresholds; floor is a minimum
    severity for conditions that are bad regardless of any number (a SUSPECT
    database, a THREADPOOL wait)."""
    subject: str
    value: Optional[float] = None
    database: Optional[str] = None
    detail: str = ""
    floor: Optional[str] = None


@dataclass(frozen=True)
class Occurrence:
    """One event-alert occurrence. dedup_key makes re-reads idempotent."""
    dedup_key: str
    occurred_at: datetime
    subject: str
    value: Optional[float] = None
    database: Optional[str] = None
    detail: str = ""
    floor: Optional[str] = None


@dataclass(frozen=True)
class EffectiveSetting:
    enabled: bool
    warning: Optional[float]
    critical: Optional[float]
    tier: str
    confirm_samples: int
    excluded_databases: FrozenSet[str] = frozenset()


@dataclass
class CheckContext:
    """What a check sees: the instance, its settings, and persistent memory
    (watermarks and baselines) that the engine saves after the check."""
    instance_name: str
    connection_string: Optional[str]
    setting: EffectiveSetting
    memory: Dict[str, Any]
    now: datetime
    run_query: Optional[Callable[[str], Awaitable[List[Dict[str, Any]]]]] = None
    cache: Dict[str, Any] = field(default_factory=dict)

    async def query(self, sql: str) -> List[Dict[str, Any]]:
        return await self.run_query(sql)

    async def cached(self, key: str, sql: str) -> List[Dict[str, Any]]:
        """Share one query between checks of the same instance and cycle."""
        if key not in self.cache:
            self.cache[key] = await self.query(sql)
        return self.cache[key]


class AlertSettingInput(BaseModel):
    """Null fields inherit from the fleet-wide row, then the catalog default."""
    model_config = ConfigDict(extra="forbid")
    alert_key: str = Field(min_length=1, max_length=80)
    instance_name: str = Field(default="", max_length=200)
    enabled: Optional[bool] = None
    warning_threshold: Optional[float] = Field(default=None, allow_inf_nan=False)
    critical_threshold: Optional[float] = Field(default=None, allow_inf_nan=False)
    tier: Optional[Tier] = None
    confirm_samples: Optional[int] = Field(default=None, ge=1, le=10)
    excluded_databases: Optional[List[str]] = Field(default=None, max_length=200)


class DigestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    hour_utc: int = Field(default=7, ge=0, le=23)
    channel_ids: List[int] = Field(default_factory=list, max_length=20)
