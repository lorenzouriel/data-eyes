"""
Configuration module for Data Eyes MCP Server.

Loads settings from environment variables using Pydantic BaseSettings.
Supports .env file for local development.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database connection
    MSSQL_CONNECTION_STRING: str
    MSSQL_CONNECTION_TIMEOUT: int = 30  # seconds
    MSSQL_QUERY_TIMEOUT: int = 30  # seconds
    MSSQL_MAX_POOL_SIZE: int = 10

    # Character encoding for pyodbc (fixes garbled non-ASCII, e.g. accented text).
    # MSSQL_WIDE_ENCODING is used for wide SQL_WCHAR/NVARCHAR decoding AND for the
    # query/parameter send encoding — SQL Server expects UTF-16LE, so leave this at
    # the default unless you know otherwise. MSSQL_ENCODING covers narrow
    # SQL_CHAR/VARCHAR decoding; override it (e.g. "cp1250") if VARCHAR data uses a
    # legacy code-page collation.
    MSSQL_ENCODING: str = "utf-8"
    MSSQL_WIDE_ENCODING: str = "utf-16-le"

    # Optional credential override. When set, these take precedence over any
    # UID/PWD embedded in MSSQL_CONNECTION_STRING, letting each deployment run
    # under its own SQL login (and thus its own read/write permissions) without
    # editing the base connection string. Leave unset to use the connection
    # string as-is.
    MSSQL_USER: Optional[str] = None
    MSSQL_PASSWORD: Optional[str] = None
    # Windows/Integrated authentication. True forces Trusted_Connection=yes
    # (ignores user/password); False forces SQL auth; None leaves it untouched.
    MSSQL_TRUSTED_CONNECTION: Optional[bool] = None

    # Optional default database (initial catalog). When set, connections open in
    # this database instead of the login's default, so unqualified names and the
    # discovery tools resolve there. Leave unset to use the login's default DB.
    # Per-call `database` arguments and fully-qualified names still work and win.
    DEFAULT_DATABASE: Optional[str] = None

    # Optional: the Data Eyes dashboard's own trend-history repository
    # (dashboard/repository/init.sql) — a Postgres database, never a
    # monitored SQL Server. When set, this server also exposes
    # repository_tools.py's tools (list_tracked_instances, get_severity_trend,
    # get_latest_snapshot) so an agent can ask "how has this looked over
    # time" using the dashboard's own collected history, not just live DMVs.
    # Leave unset to run this server exactly as before, with no dashboard
    # dependency at all.
    REPOSITORY_DSN: Optional[str] = None

    # Security & safety
    READ_ONLY: bool = True
    ENABLE_WRITES: bool = False
    ADMIN_CONFIRM: str = ""  # must be set to a specific token to enable writes
    MAX_ROWS_PER_QUERY: int = 50000
    MAX_QUERY_LENGTH: int = 50000  # characters

    # Feature flags
    ENABLE_METRICS: bool = True
    ENABLE_HEALTH_CHECKS: bool = True
    ENABLE_SCHEMA_DISCOVERY: bool = True

    # Server configuration
    MCP_TRANSPORT: str = "stdio"  # 'stdio' or 'http'
    HTTP_BIND_HOST: str = "127.0.0.1"
    HTTP_BIND_PORT: int = 8080

    # DNS rebinding protection (HTTP transport).
    # By default only localhost/127.0.0.1 are accepted. Set this to the server's
    # external hostname (without port) to allow access via that host, e.g.
    # "mcp.example.com". Leave unset for local-only use.
    ALLOWED_HOST: Optional[str] = None

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # 'json' or 'text'

    # Observability
    ENABLE_PROMETHEUS: bool = True
    SENTRY_DSN: Optional[str] = None

    # Rate limiting
    RATE_LIMIT_QUERIES_PER_MINUTE: int = 1000
    RATE_LIMIT_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=False,
    )


# Global settings singleton
settings = Settings()


def get_settings() -> Settings:
    """Get global settings instance."""
    return settings


def validate_settings() -> tuple[bool, Optional[str]]:
    """
    Validate critical settings. Returns (is_valid, error_message).
    """
    if not settings.MSSQL_CONNECTION_STRING:
        return False, "MSSQL_CONNECTION_STRING must be set"

    if settings.ENABLE_WRITES and not settings.ADMIN_CONFIRM:
        return False, "ADMIN_CONFIRM must be set to enable writes"

    if settings.MSSQL_QUERY_TIMEOUT < 1:
        return False, "MSSQL_QUERY_TIMEOUT must be >= 1 second"

    if settings.MAX_ROWS_PER_QUERY < 1:
        return False, "MAX_ROWS_PER_QUERY must be >= 1"

    return True, None
