"""Importing the check modules registers every check in CHECKS."""

from app.alerts.checks import availability  # noqa: F401
from app.alerts.checks import backups  # noqa: F401
from app.alerts.checks import maintenance  # noqa: F401
from app.alerts.checks import performance  # noqa: F401
from app.alerts.checks import security  # noqa: F401
from app.alerts.checks import storage  # noqa: F401
from app.alerts.checks.registry import CHECKS

__all__ = ["CHECKS"]
