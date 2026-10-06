"""Application startup and background worker lifecycle."""
import app.infrastructure.postgres.pool as postgres_pool
import app.infrastructure.postgres.schema as postgres_schema
import app.modules.instances.repository as instances_repository
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.modules.monitoring import collector
from app.modules.insights import sweep as insights_sweep
from app.modules.auth.router import ensure_bootstrap_admin
from app.core.config import load_seed_instances
from app.core.config import settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await postgres_schema.ensure_security_schema()
    await postgres_schema.ensure_notification_schema()
    await postgres_schema.ensure_alert_schema()
    # Security schema migration above requires a healthy repository and fails
    # closed. Synchronize YAML instances and seed an admin only for an empty
    # user table. Later seed errors are logged so existing registry data remains
    # usable after a transient failure.
    try:
        seeded = await instances_repository.seed_instances_from_yaml(load_seed_instances())
        if seeded:
            logger.info("Synchronized %d instance(s) from %s", seeded, settings.INSTANCES_FILE)
    except postgres_pool.RepositoryUnavailable as e:
        logger.error("Could not seed instances at startup: %s", e)
    try:
        if await ensure_bootstrap_admin():
            logger.info("Seeded bootstrap admin account '%s'", settings.DASHBOARD_ADMIN_USERNAME)
    except postgres_pool.RepositoryUnavailable as e:
        logger.error("Could not seed bootstrap admin at startup: %s", e)

    # Starts the trend-history collector and the insights sweep (a no-op if
    # the selected AI provider isn't configured — see insights_sweep.start()), and
    # tears both down cleanly on shutdown so the repository connection pool
    # doesn't leak.
    collector.start()
    insights_sweep.start()
    try:
        yield
    finally:
        collector.stop()
        insights_sweep.stop()
        await postgres_pool.close_pool()
