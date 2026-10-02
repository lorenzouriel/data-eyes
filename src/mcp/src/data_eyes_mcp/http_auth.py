"""Authenticate HTTP callers using deployment-scoped, hashed bearer tokens.

Identity headers are never an authentication source. Only /health is public.
Token hashes are configured out of band; this is not an OAuth issuer.
"""

import hashlib
import hmac

from starlette.responses import JSONResponse

from .config import settings


class BearerAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        headers = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
        principal = None
        if len(headers) == 1 and len(headers[0]) <= 4096:
            scheme, _, token = headers[0].partition(b" ")
            if scheme.lower() == b"bearer" and token and not any(c in token for c in (b" ", b"\t", b"\r", b"\n")):
                digest = hashlib.sha256(token).hexdigest()
                for name, expected in settings.HTTP_TOKEN_HASHES.items():
                    if hmac.compare_digest(digest, expected):
                        principal = name
        if principal is None:
            response = JSONResponse({"detail": "Valid bearer token required"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
            return await response(scope, receive, send)
        scope["data_eyes.principal"] = principal
        await self.app(scope, receive, send)
