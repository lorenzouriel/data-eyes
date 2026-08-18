"""
Data Eyes dashboard backend — FastAPI app.

Replaces monitor/'s Grafana stack. Serves the Main Page (fleet-wide health
summary, GET /api/fleet), the per-database DPA-style tabbed drill-down
(GET /api/instances/:id, GET /api/instances/:id/databases/:db/tabs/:tab),
trend history (GET /api/instances/:id/trend/:category), and the embedded
insights agent (GET /api/insights/feed, SSE streams, POST /api/insights/explain).
Talks to each monitored SQL Server instance directly (app/mssql_client.py,
app/diagnostics.py) rather than through an MCP server — MCP
(mcp/src/data_eyes_mcp/) is reserved for agent use (Claude Code's
sql-server-dba agent), not this backend's own rendering/collection path.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import collector, insights_sweep, repository
from .auth import ensure_bootstrap_admin
from .auth import router as auth_router
from .config import load_seed_instances, settings
from .routers.databases import router as databases_router
from .routers.fleet import router as fleet_router
from .routers.health import router as health_router
from .routers.insights import router as insights_router
from .routers.instances import router as instances_router
from .routers.trends import router as trends_router
from .routers.users import router as users_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One-time startup seeding: instances.yaml -> instance table (only
    # inserts entries not already registered — see
    # repository.seed_instances_from_yaml()), and the bootstrap admin
    # account if the user table is empty (see auth.ensure_bootstrap_admin()).
    # A repository outage at boot is logged, not fatal — the app still
    # starts, just with whatever the DB currently holds (nothing, on a first
    # boot against a cold Postgres that isn't ready yet).
    try:
        seeded = await repository.seed_instances_from_yaml(load_seed_instances())
        if seeded:
            logger.info("Seeded %d instance(s) from %s", seeded, settings.INSTANCES_FILE)
    except repository.RepositoryUnavailable as e:
        logger.error("Could not seed instances at startup: %s", e)
    try:
        if await ensure_bootstrap_admin():
            logger.info("Seeded bootstrap admin account '%s'", settings.DASHBOARD_ADMIN_USERNAME)
    except repository.RepositoryUnavailable as e:
        logger.error("Could not seed bootstrap admin at startup: %s", e)

    # Starts the trend-history collector and the insights sweep (a no-op if
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
        await repository.close_pool()


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
app.include_router(users_router)
app.include_router(fleet_router)
app.include_router(instances_router)
app.include_router(databases_router)
app.include_router(trends_router)
app.include_router(insights_router)
