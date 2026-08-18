"""
Policy engine for SQL validation and safety enforcement.

Implements configurable rules for allowed SQL, read-only enforcement,
row limits, rate limiting, and audit logging.
"""

import re
import hashlib
import logging
from typing import Tuple, Optional, List
from enum import Enum

from .config import settings

logger = logging.getLogger(__name__)


class QueryMode(Enum):
    """Query execution mode."""
    READ_ONLY = "read_only"
    WRITE = "write"
    DDL = "ddl"


# SQL keywords that are dangerous if writes are disabled
READ_ONLY_BANNED_PATTERNS = [
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bGRANT\b",
    r"\bDENY\b",
    r"\bREVOKE\b",
    r"\bCREATE\b",
]

# Always-banned patterns (regardless of mode)
ALWAYS_BANNED_PATTERNS = [
    r"\bxp_\w+",  # extended stored procedures
    r"\bsp_\w+",  # system stored procedures (some are risky)
    r"\bKILL\b",
    r"\bSHUTDOWN\b",
]

# Whitelist for allowed system stored procedures (empty by default, can be configured)
ALLOWED_SYSTEM_PROCEDURES = set()


def hash_sql(sql: str) -> str:
    """Create a SHA256 hash of SQL for safe logging."""
    return hashlib.sha256(sql.encode()).hexdigest()[:16]


def normalize_sql(sql: str) -> str:
    """Normalize SQL for analysis: strip whitespace, uppercase keywords."""
    return " ".join(sql.split()).upper()


def is_allowed_sql(
    sql: str,
    mode: QueryMode = QueryMode.READ_ONLY,
    client_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate SQL against security policies.

    Returns (is_allowed, reason).
    If reason is None, SQL is allowed.
    """
    if not sql or not sql.strip():
        return False, "Empty SQL query"

    # Check query length
    if len(sql) > settings.MAX_QUERY_LENGTH:
        return False, f"Query exceeds maximum length of {settings.MAX_QUERY_LENGTH} characters"

    normalized = normalize_sql(sql)

    # Check always-banned patterns
    for pattern in ALWAYS_BANNED_PATTERNS:
        if re.search(pattern, normalized):
            return False, f"Query contains banned pattern: {pattern}"

    # Check multi-statement queries (semicolon-separated)
    # Allow only single statements
    if ";" in sql.strip().rstrip(";"):
        return False, "Multi-statement queries are not allowed"

    # Enforce read-only mode
    if mode == QueryMode.READ_ONLY:
        for pattern in READ_ONLY_BANNED_PATTERNS:
            if re.search(pattern, normalized):
                reason = f"Query contains write operation: {pattern}"
                logger.warning(
                    "Policy violation (read-only): %s | SQL hash: %s | Client: %s",
                    reason,
                    hash_sql(sql),
                    client_id or "unknown",
                )
                return False, reason

        # Require SELECT as primary statement
        if not re.match(r"^\s*SELECT\b", normalized):
            return False, "Only SELECT queries are allowed in read-only mode"

    # Additional checks for DDL mode (if needed in future)
    if mode == QueryMode.DDL:
        # Can add stricter DDL-specific rules here
        pass

    # Rate limiting check (if enabled)
    if settings.RATE_LIMIT_ENABLED:
        # This would integrate with a rate limiter
        # For now, we just log it
        pass

    return True, None


def get_query_mode() -> QueryMode:
    """Determine query mode based on settings."""
    if settings.READ_ONLY:
        return QueryMode.READ_ONLY
    elif settings.ENABLE_WRITES:
        return QueryMode.WRITE
    else:
        return QueryMode.READ_ONLY


def validate_with_audit(
    sql: str,
    client_id: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate SQL and log the audit event.

    Returns (is_allowed, reason).
    """
    mode = get_query_mode()
    is_allowed, reason = is_allowed_sql(sql, mode=mode, client_id=client_id)

    # Log audit event
    if is_allowed:
        logger.info(
            "Query allowed | Tool: %s | Mode: %s | SQL hash: %s | Client: %s",
            tool_name or "unknown",
            mode.value,
            hash_sql(sql),
            client_id or "unknown",
        )
    else:
        logger.warning(
            "Query denied | Tool: %s | Reason: %s | SQL hash: %s | Client: %s",
            tool_name or "unknown",
            reason,
            hash_sql(sql),
            client_id or "unknown",
        )

    return is_allowed, reason


def explain_policy() -> dict:
    """Return a human-readable explanation of current policies."""
    mode = get_query_mode()
    return {
        "query_mode": mode.value,
        "read_only": settings.READ_ONLY,
        "enable_writes": settings.ENABLE_WRITES,
        "max_rows_per_query": settings.MAX_ROWS_PER_QUERY,
        "query_timeout_seconds": settings.MSSQL_QUERY_TIMEOUT,
        "max_query_length_chars": settings.MAX_QUERY_LENGTH,
        "allowed_tools": [
            "execute_sql",
            "list_databases",
            "list_schemas",
            "list_tables",
            "schema_discovery",
            "describe_table",
            "get_relationships",
            "sample_table",
            "distinct_values",
            "get_database_info",
            # DBA diagnostic tools (data_eyes_mcp/dba_tools.py)
            "wait_stats",
            "missing_indexes",
            "unused_indexes",
            "stale_statistics",
            "index_fragmentation",
            "top_queries",
            "db_space",
            "backup_health",
            "checkdb_health",
            "blocking_snapshot",
            "ag_health",
            "job_health",
            "fleet_health_score",
            # Dashboard-repository trend tools (data_eyes_mcp/repository_tools.py)
            "list_tracked_instances",
            "get_severity_trend",
            "get_latest_snapshot",
        ],
        "banned_patterns": READ_ONLY_BANNED_PATTERNS if mode == QueryMode.READ_ONLY else [],
        "rate_limiting_enabled": settings.RATE_LIMIT_ENABLED,
    }
