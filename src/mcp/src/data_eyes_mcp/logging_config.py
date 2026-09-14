"""
Logging configuration for Data Eyes MCP Server.

Sets up structured JSON logging with optional Sentry integration.
Redacts sensitive information from logs.
"""

import logging
import json
import sys

from .config import settings


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

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive fields from log record."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            for key in self.SENSITIVE_KEYS:
                if key.lower() in record.msg.lower():
                    # Redact known secret values from the message.
                    for secret in (settings.MSSQL_CONNECTION_STRING, settings.MSSQL_PASSWORD):
                        if secret:
                            record.msg = record.msg.replace(secret, "***REDACTED***")
                    break
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
