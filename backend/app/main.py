"""
Data Eyes dashboard backend — FastAPI app.

Replaces monitor/'s Grafana stack. Serves Fleet Status (GET /api/fleet), the
per-instance tabbed drill-down (GET /api/instances/:id/overview,
GET /api/instances/:id/tabs/:tab), trend history (GET /api/instances/:id/trend/:category),
and the embedded insights agent (GET /api/insights/feed, SSE streams,
POST /api/insights/explain, POST /api/insights/instances/:id/advisor,
POST /api/insights/ask).
Talks to each monitored SQL Server instance directly (app/infrastructure/sqlserver/client.py,
app/modules/monitoring/diagnostics) rather than through an MCP server — MCP
(mcp/src/data_eyes_mcp/) is reserved for agent use (Claude Code's
sql-server-dba agent), not this backend's own rendering/collection path.
"""


import logging

from app.lifespan import lifespan
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.modules.auth.router import router as auth_router
from app.core.config import settings
from app.modules.monitoring.activity_router import router as activity_router
from app.modules.monitoring.fleet_router import router as fleet_router
from app.infrastructure.health import router as health_router
from app.modules.insights.router import router as insights_router
from app.modules.monitoring.instance_tabs_router import router as instance_tabs_router
from app.modules.instances.router import router as instances_router
from app.modules.monitoring.trends_router import router as trends_router
from app.modules.users.router import router as users_router
from app.modules.notifications.router import router as notifications_router
from app.modules.alerts.router import router as alerts_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


app = FastAPI(title="Data Eyes Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE_SECONDS,
    same_site="strict",
    https_only=settings.SESSION_HTTPS_ONLY,
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
app.include_router(instance_tabs_router)
app.include_router(trends_router)
app.include_router(activity_router)
app.include_router(insights_router)
app.include_router(notifications_router)
app.include_router(alerts_router)
