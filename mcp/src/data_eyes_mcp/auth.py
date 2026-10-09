"""Who is calling, and may they use this tool on this instance.

HTTP callers are identified only by a bearer token whose SHA-256 hash is in
HTTP_TOKEN_HASHES; identity headers are never trusted. stdio uses
DEFAULT_PRINCIPAL. Grants are fnmatch patterns over tool and instance names.
"""

import fnmatch
import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from starlette.responses import JSONResponse

from data_eyes_mcp.config import load_fleet, settings

audit_log = logging.getLogger("data_eyes_mcp.audit")
PUBLIC_PATHS = {"/health"}
http_mode = False  # set by main.py; HTTP never falls back to DEFAULT_PRINCIPAL
_calls: dict = defaultdict(deque)
_calls_lock = Lock()


class AuthorizationError(PermissionError):
    pass


class BearerAuthMiddleware:
    """ASGI middleware: every HTTP or websocket request except /health needs a token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan" or scope.get("path") in PUBLIC_PATHS:
            return await self.app(scope, receive, send)
        principal = self._principal(scope.get("headers", []))
        if principal is None:
            response = JSONResponse({"detail": "Valid bearer token required"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
            return await response(scope, receive, send)
        scope["data_eyes.principal"] = principal
        await self.app(scope, receive, send)

    @staticmethod
    def _principal(headers) -> Optional[str]:
        values = [value for key, value in headers if key.lower() == b"authorization"]
        if len(values) != 1 or len(values[0]) > 4096:
            return None
        scheme, _, token = values[0].partition(b" ")
        if scheme.lower() != b"bearer" or not token or any(c in token for c in b" \t\r\n"):
            return None
        digest = hashlib.sha256(token).hexdigest()
        match = None
        for name, expected in settings.HTTP_TOKEN_HASHES.items():  # no early exit: constant time
            if hmac.compare_digest(digest, expected):
                match = name
        return match


def principal_of(ctx) -> str:
    """The authenticated principal for this tool call."""
    try:
        request = ctx.request_context.request if ctx is not None else None
    except (AttributeError, ValueError):
        request = None
    if request is not None:
        principal = request.scope.get("data_eyes.principal")
        if not principal:
            raise AuthorizationError("Authenticated HTTP context required")
        return principal
    if http_mode:
        raise AuthorizationError("Authenticated HTTP context required")
    if not settings.DEFAULT_PRINCIPAL:
        raise AuthorizationError("DEFAULT_PRINCIPAL is not set")
    return settings.DEFAULT_PRINCIPAL


def audit(decision: str, reason: str, **fields) -> None:
    log = audit_log.info if decision == "allow" else audit_log.warning
    log("security_audit %s", json.dumps({"decision": decision, "reason": reason, **fields}, default=str, sort_keys=True))


def allowed(principal: str, tool: str, instance: Optional[str] = None) -> bool:
    policy = load_fleet().principals.get(principal)
    if policy is None or not _matches(tool, policy.tools):
        return False
    return instance is None or _matches(instance, policy.instances)


def authorize(principal: str, tool: str, instance: Optional[str] = None) -> None:
    """Default deny: raise unless the principal is granted the tool (and instance)."""
    if not allowed(principal, tool, instance):
        audit("deny", "not_granted", principal=principal, tool=tool, instance=instance)
        raise AuthorizationError(f"{principal!r} may not use {tool!r}" + (f" on {instance!r}" if instance else ""))
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit:
        now = time.monotonic()
        with _calls_lock:
            window = _calls[principal]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= limit:
                audit("deny", "rate_limited", principal=principal, tool=tool, instance=instance)
                raise AuthorizationError("Rate limit exceeded; retry in a minute")
            window.append(now)


def _matches(value: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(value.casefold(), pattern.casefold()) for pattern in patterns)
