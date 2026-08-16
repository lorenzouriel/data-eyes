"""
Data Eyes dashboard backend — FastAPI app.

Replaces monitor/'s Grafana stack. Serves the Main Page (fleet-wide health
summary, GET /api/fleet) and, from Phase 3 onward, the per-database
DPA-style drill-down. Talks to each monitored instance through its own
data-eyes-mcp server (mcp_client.py) rather than connecting to SQL Server
directly — the MCP servers already own connection pooling, credentials, and
the read-only policy gate (mcp/src/data_eyes_mcp/policy.py); this backend
does not duplicate that.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import router as auth_router
from .config import settings
from .routers.fleet import router as fleet_router
from .routers.health import router as health_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Data Eyes Dashboard", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE_SECONDS,
    same_site="lax",
)

if settings.CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(fleet_router)
