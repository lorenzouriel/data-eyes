"""Context implementation."""

import base64
from typing import Optional, cast
from mcp.server.fastmcp import Context
from data_eyes_mcp.core.config import settings
from data_eyes_mcp.security.authorization import AuthorizationError
import logging
logger = logging.getLogger(__name__)


_HDR_USER = "X-MSSQL-User"


_HDR_PASSWORD = "X-MSSQL-Password"


_HDR_TRUSTED = "X-MSSQL-Trusted-Connection"


_HDR_INSTANCE = "X-Data-Eyes-Instance"


_B64_SUFFIX = "-B64"


def _header_value(headers, name: str) -> Optional[str]:
    """Return a header's value, preferring its base64 variant (<name>-B64).

    The base64 form lets clients pass values containing non-Latin-1 characters,
    which raw HTTP headers cannot carry.
    """
    b64 = headers.get(name + _B64_SUFFIX)
    if b64:
        try:
            return base64.b64decode(b64).decode("utf-8")
        except Exception:
            logger.warning("Ignoring malformed base64 header: %s", name + _B64_SUFFIX)
            return None
    return cast(Optional[str], headers.get(name))


def _creds_from_ctx(ctx: Optional[Context]) -> dict:
    """Extract optional per-request SQL credentials from the MCP request headers.

    Returns a dict suitable for request_credentials(**...); empty when none are
    provided (e.g. stdio transport, or a client that sends no credential headers).
    """
    request = None
    if ctx is not None:
        try:
            request = ctx.request_context.request
        except (AttributeError, ValueError):
            pass
    if request is None:
        if settings.MCP_TRANSPORT == "http":
            raise AuthorizationError("Authenticated HTTP context required")
        return {}
    principal = request.scope.get("data_eyes.principal")
    if not principal:
        raise AuthorizationError("Authenticated HTTP context required")
    headers = request.headers

    creds: dict = {"principal": principal}
    user = _header_value(headers, _HDR_USER)
    password = _header_value(headers, _HDR_PASSWORD)
    trusted_raw = _header_value(headers, _HDR_TRUSTED)
    instance = _header_value(headers, _HDR_INSTANCE)
    if user:
        creds["user"] = user
    if password:
        creds["password"] = password
    if trusted_raw is not None:
        creds["trusted"] = trusted_raw.strip().lower() in ("1", "true", "yes", "on")
    if instance:
        creds["instance"] = instance
    return creds


def _connection_options(ctx: Optional[Context], instance: Optional[str]) -> dict:
    """Combine HTTP header overrides with an explicit MCP tool argument."""
    options = _creds_from_ctx(ctx)
    if instance:
        options["instance"] = instance
    return options
