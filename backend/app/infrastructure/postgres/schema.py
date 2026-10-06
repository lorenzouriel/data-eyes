"""Schema implementation."""

from app.infrastructure.postgres.pool import _acquire
from app.modules.notifications.repository import notification_connection


async def ensure_security_schema():
    from pathlib import Path
    async with await _acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20260926)")
            await conn.execute(Path(__file__).with_name("security_schema.sql").read_text())


async def ensure_notification_schema():
    from pathlib import Path
    async with notification_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261002)")
            await conn.execute(Path(__file__).with_name("notification_schema.sql").read_text(encoding="utf-8"))


async def ensure_alert_schema():
    from pathlib import Path
    async with notification_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261005)")
            await conn.execute(Path(__file__).with_name("alert_schema.sql").read_text(encoding="utf-8"))
