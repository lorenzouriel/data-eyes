"""Default-deny MCP authorization, rate limiting, and security audit context.

Authentication is intentionally out of scope for now. A principal from an HTTP
header is trustworthy only when a protected upstream proxy removes caller-sent
copies and injects the verified identity. Stdio deployments should use
DEFAULT_PRINCIPAL.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock
from typing import Iterable, Optional

from .config import load_security_config, settings

logger = logging.getLogger("data_eyes_mcp.security_audit")

_principal: ContextVar[str] = ContextVar("security_principal", default="anonymous")
_tool: ContextVar[str] = ContextVar("security_tool", default="unknown")
_instance: ContextVar[Optional[str]] = ContextVar("security_instance", default=None)
_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


class AuthorizationError(PermissionError):
    pass


class RateLimitError(AuthorizationError):
    pass


@dataclass(frozen=True)
class SecurityContext:
    principal: str
    tool: str
    instance: Optional[str]


def set_principal(value: Optional[str]):
    return _principal.set((value or settings.DEFAULT_PRINCIPAL or "anonymous").strip())


def reset_principal(token) -> None:
    _principal.reset(token)


def set_tool(value: str):
    return _tool.set(value)


def reset_tool(token) -> None:
    _tool.reset(token)


def set_instance(value: Optional[str]):
    return _instance.set(value)


def reset_instance(token) -> None:
    _instance.reset(token)


def current_context() -> SecurityContext:
    return SecurityContext(_principal.get(), _tool.get(), _instance.get())


def _matches(value: Optional[str], patterns: Iterable[str]) -> bool:
    candidate = value or ""
    return any(fnmatch.fnmatchcase(candidate.casefold(), pattern.casefold()) for pattern in patterns)


def audit(decision: str, reason: str, **fields) -> None:
    ctx = current_context()
    event = {
        "event": "mcp_authorization",
        "decision": decision,
        "reason": reason,
        "principal": ctx.principal,
        "tool": ctx.tool,
        "instance": ctx.instance,
        **fields,
    }
    log = logger.info if decision == "allow" else logger.warning
    log("security_audit %s", json.dumps(event, default=str, sort_keys=True))


def authorize(  # noqa: C901
    *,
    instance: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    table: Optional[str] = None,
    columns: Optional[Iterable[str]] = None,
    tool: Optional[str] = None,
) -> None:
    """Require an explicit matching grant. No principal or empty grants deny."""
    if not settings.SECURITY_ENFORCEMENT:
        return
    ctx = current_context()
    principal = ctx.principal
    tool_name = tool or ctx.tool
    instance_name = instance or ctx.instance
    policy = load_security_config().principals.get(principal)
    fields = {
        "tool": tool_name,
        "instance": instance_name,
        "database": database,
        "schema": schema,
        "table": table,
    }
    if policy is None:
        audit("deny", "unknown_principal", **fields)
        raise AuthorizationError(f"principal {principal!r} has no security policy")
    if not _matches(tool_name, policy.tools):
        audit("deny", "tool_not_allowed", **fields)
        raise AuthorizationError(f"tool {tool_name!r} is not allowed")
    if instance_name and not _matches(instance_name, policy.instances):
        audit("deny", "instance_not_allowed", **fields)
        raise AuthorizationError(f"instance {instance_name!r} is not allowed")

    # Tools without an object target stop at tool+instance authorization.
    if database is None and schema is None and table is None and not columns:
        audit("allow", "tool_instance_grant", **fields)
        return

    requested_columns = list(columns or [])
    for grant in policy.objects:
        if database is not None and not _matches(database, grant.databases):
            continue
        if schema is not None and not _matches(schema, grant.schemas):
            continue
        if table is not None and not _matches(table, grant.tables):
            continue
        if requested_columns and not all(_matches(column, grant.columns) for column in requested_columns):
            continue
        audit("allow", "object_grant", **fields)
        return
    audit("deny", "object_not_allowed", **fields)
    raise AuthorizationError("database object is not allowed by policy")


def is_authorized(**target) -> bool:
    try:
        authorize(**target)
        return True
    except AuthorizationError:
        return False


def enforce_rate_limit() -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    key = current_context().principal
    now = time.monotonic()
    with _rate_lock:
        window = _windows[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= settings.RATE_LIMIT_QUERIES_PER_MINUTE:
            audit("deny", "rate_limit_exceeded")
            raise RateLimitError("per-principal query rate limit exceeded")
        window.append(now)


def split_qualified_name(value: str, default_database: Optional[str] = None):
    """Return database/schema/table for a one-to-three-part T-SQL name."""
    parts = [part.strip().strip("[]\"") for part in value.split(".")]
    if len(parts) == 1:
        return default_database, "dbo", parts[0]
    if len(parts) == 2:
        return default_database, parts[0], parts[1]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    raise AuthorizationError("four-part and external object names are not allowed")


_FROM_JOIN = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\[[^]]+\]|[A-Za-z_][\w$#]*)(?:\s*\.\s*(?:\[[^]]+\]|[A-Za-z_][\w$#]*)){0,3})",
    re.IGNORECASE,
)


def authorize_adhoc_sql(sql: str, database: Optional[str], instance: Optional[str]) -> None:
    """Authorize every base object referenced by an already validated SELECT.

    Sensitive deployments disable ad-hoc SQL entirely. This extractor is then
    only a secondary object-authorization check for enabled environments; SQL
    Server grants remain the final boundary.
    """
    authorize(instance=instance, database=database, tool="execute_sql")
    refs = _FROM_JOIN.findall(sql)
    if not refs:
        raise AuthorizationError("ad-hoc query must reference an authorized table")
    projection_match = re.match(r"\s*SELECT\s+(?:TOP\s*(?:\([^)]*\)|\d+)\s+)?(.*?)\s+FROM\s", sql, re.I | re.S)
    if not projection_match:
        raise AuthorizationError("ad-hoc SELECT projection could not be safely analyzed")
    projection = projection_match.group(1).strip()
    if "*" in projection:
        requested_columns = ["*"]
    else:
        requested_columns = []
        for item in projection.split(","):
            expression = re.sub(r"\s+AS\s+.+$", "", item.strip(), flags=re.I)
            # Only direct column references are accepted by this conservative
            # secondary parser. Use fixed tools for expressions/aggregates.
            if not re.fullmatch(r"(?:\[[^]]+\]|[A-Za-z_]\w*)(?:\.(?:\[[^]]+\]|[A-Za-z_]\w*))*", expression):
                raise AuthorizationError("ad-hoc SELECT must use explicit direct columns")
            requested_columns.append(expression.split(".")[-1].strip("[]"))
    for ref in refs:
        db, schema, table = split_qualified_name(re.sub(r"\s+", "", ref), database)
        authorize(
            instance=instance,
            database=db,
            schema=schema,
            table=table,
            columns=requested_columns,
            tool="execute_sql",
        )
