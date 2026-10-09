"""Entry point: python -m data_eyes_mcp.main [--transport stdio|http] [--bind host:port]."""

import argparse
import json
import logging
import os
import sys

from data_eyes_mcp import auth
from data_eyes_mcp.config import load_fleet, settings, validate


class _Redact(logging.Filter):
    """Remove passwords and connection strings from every log message."""

    def __init__(self) -> None:
        super().__init__()
        secrets = {value for key, value in os.environ.items() if key.endswith("_MSSQL_PASSWORD")}
        try:
            secrets |= {instance.mssql_connection_string for instance in load_fleet().instances.values()}
        except ValueError:
            pass  # validate() reports the broken fleet file
        self.secrets = sorted((s for s in secrets if s), key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "***REDACTED***")
        record.msg, record.args = message, None
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"timestamp": self.formatTime(record), "level": record.levelname,
                 "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(level: str, fmt: str) -> None:
    handler = logging.StreamHandler(sys.stderr)  # stdout carries stdio JSON-RPC
    handler.addFilter(_Redact())
    handler.setFormatter(_JsonFormatter() if fmt == "json" else
                         logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)


def run() -> None:
    parser = argparse.ArgumentParser(description="Data Eyes MCP server for the SQL Server fleet in instances.yaml")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--bind", default="127.0.0.1:8080", help="host:port for --transport http")
    parser.add_argument("--log-level", default=settings.LOG_LEVEL)
    parser.add_argument("--log-format", choices=["json", "text"], default=settings.LOG_FORMAT)
    args = parser.parse_args()

    auth.http_mode = args.transport == "http"
    setup_logging(args.log_level, args.log_format)
    try:
        validate(args.transport)
    except ValueError as exc:
        logging.getLogger(__name__).error("Configuration error: %s", exc)
        sys.exit(1)

    from data_eyes_mcp.tools import mcp

    if args.transport == "stdio":
        mcp.run("stdio")
        return

    import uvicorn
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "alive"})

    host, _, port = args.bind.rpartition(":")
    uvicorn.run(auth.BearerAuthMiddleware(mcp.streamable_http_app()), host=host, port=int(port),
                proxy_headers=False, log_config=None)


if __name__ == "__main__":
    run()
