"""
Data Eyes dashboard backend — FastAPI app.

Replaces monitor/'s Grafana stack. Serves the Main Page (fleet-wide health
summary, GET /api/fleet), the per-database DPA-style tabbed drill-down
(GET /api/instances/:id, GET /api/instances/:id/databases/:db/tabs/:tab),
trend history (GET /api/instances/:id/trend/:category), and the embedded
insights agent (GET /api/insights/feed, SSE streams, POST /api/insights/explain).
Talks to each monitored instance through its own
data-eyes-mcp server (mcp_client.py) rather than connecting to SQL Server
directly — the MCP servers already own connection pooling, credentials, and
the read-only policy gate (mcp/src/data_eyes_mcp/policy.py); this backend
does not duplicate that.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import collector, insights_sweep
from .auth import router as auth_router
from .config import settings
from .repository import close_pool
from .routers.databases import router as databases_router
from .routers.fleet import router as fleet_router
from .routers.health import router as health_router
from .routers.insights import router as insights_router
from .routers.instances import router as instances_router
from .routers.trends import router as trends_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Starts the trend-history collector (a no-op if REPOSITORY_DSN isn't
    # configured — see collector.start()) and the insights sweep (a no-op if
    # ANTHROPIC_API_KEY isn't configured — see insights_sweep.start()), and
    # tears both down cleanly on shutdown so the repository connection pool
    # doesn't leak.
    collector.start()
    insights_sweep.start()
    try:
        yield
    finally:
        collector.stop()
        insights_sweep.stop()
        await close_pool()


app = FastAPI(title="Data Eyes Dashboard", version="0.1.0", lifespan=lifespan)

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
app.include_router(instances_router)
app.include_router(databases_router)
app.include_router(trends_router)
app.include_router(insights_router)
