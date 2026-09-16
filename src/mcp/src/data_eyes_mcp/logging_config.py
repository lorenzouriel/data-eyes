"""
Logging configuration for Data Eyes MCP Server.

Sets up structured JSON logging with optional Sentry integration.
Redacts sensitive information from logs.
"""

import json
import logging
import os
import sys

from .config import load_instances, settings


class SensitiveDataFilter(logging.Filter):
    """
    Filter to redact sensitive data from logs.
    Masks connection strings, passwords, and other PII.
    """

    SENSITIVE_KEYS = {
        "password",
        "passwd",
        "pwd",
        "connection_string",
        "MSSQL_CONNECTION_STRING",
        "MSSQL_PASSWORD",
        "auth_token",
        "token",
        "api_key",
        "secret",
    }

    def __init__(self) -> None:
        super().__init__()
        self.secrets = {settings.MSSQL_CONNECTION_STRING, settings.MSSQL_PASSWORD}
        try:
            self.secrets.update(item.mssql_connection_string for item in load_instances())
        except Exception:
            pass
        self.secrets.update(
            value
            for key, value in os.environ.items()
            if value and (key.endswith("_MSSQL_PASSWORD") or key.endswith("_CONNECTION_STRING"))
        )
        self.secrets.discard(None)

    def _redact(self, value):
        if not isinstance(value, str):
            return value
        for secret in self.secrets:
            value = value.replace(secret, "***REDACTED***")
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive fields from log record."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: self._redact(value) for key, value in record.args.items()}
        return True


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON."""
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_obj.update(record.extra)

        return json.dumps(log_obj)


def setup_logging() -> None:
    """
    Configure logging based on settings.

    Sets up:
    - Console handler with appropriate formatter
    - Optional Sentry integration
    - Log level from config
    - Sensitive data filtering
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    # IMPORTANT: Use stderr for logs to keep stdout clean for MCP JSON-RPC messages
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)

    # Add sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    console_handler.addFilter(sensitive_filter)

    # Set formatter based on config
    formatter: logging.Formatter
    if settings.LOG_FORMAT.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Set log level for specific noisy libraries
    logging.getLogger("pyodbc").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("prometheus_client").setLevel(logging.WARNING)

    logging.info("Logging configured: level=%s format=%s", settings.LOG_LEVEL, settings.LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name."""
    return logging.getLogger(name)
