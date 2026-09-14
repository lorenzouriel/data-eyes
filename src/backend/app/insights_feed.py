"""
In-memory insights feed — a bounded ring buffer, not a database table.

Deliberately simple for v1: insights don't survive a backend restart. If
persistence-across-restarts is needed later, add an `insight` table to the
Phase 4 repository (dashboard/repository/init.sql) and prime this buffer from
it on startup — not required for the feature to be useful today.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Deque, List

from pydantic import BaseModel

from .config import settings


class Insight(BaseModel):
    instance_name: str
    category: str
    severity: str
    message: str
    created_at: str


_feed: Deque[Insight] = deque(maxlen=settings.INSIGHTS_FEED_MAX_SIZE)


def add_insight(instance_name: str, category: str, severity: str, message: str) -> None:
    _feed.appendleft(
        Insight(
            instance_name=instance_name,
            category=category,
            severity=severity,
            message=message,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def get_feed() -> List[Insight]:
    return list(_feed)
