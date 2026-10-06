"""Importing the check modules registers every check in CHECKS."""

from app.modules.alerts.checks import availability  # noqa: F401
from app.modules.alerts.checks import backups  # noqa: F401
from app.modules.alerts.checks import data_eyes  # noqa: F401
from app.modules.alerts.checks import maintenance  # noqa: F401
from app.modules.alerts.checks import performance  # noqa: F401
from app.modules.alerts.checks import security  # noqa: F401
from app.modules.alerts.checks import storage  # noqa: F401
from app.modules.alerts.checks.registry import CHECKS

__all__ = ["CHECKS"]
