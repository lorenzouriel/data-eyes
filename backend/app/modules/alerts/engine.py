"""Runs due alert checks at the end of each collector cycle.

For every instance: probe the connection first (an unreachable instance
raises only SQL Server Connection, not dozens of UNKNOWN checks), then run
each enabled check whose frequency tier is due. State alerts are written to
alert_state and, as `alert.<key>`, to metric_snapshot, where the notification
dispatcher picks up transitions. Event alerts are stored once each in
alert_event for the dispatcher's event path.

Checks run one at a time per instance, and at most two instances at once, so
alerting never exhausts the background SQL lane shared with the collector.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import app.modules.alerts.repository as alerts_repository
import app.modules.monitoring.repository as monitoring_repository
from app.core.config import settings
from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.sqlserver.client import MSSQLError
from app.modules.alerts import evaluation
from app.modules.alerts.catalog import CATALOG
from app.modules.alerts.catalog import SELF_INSTANCE
from app.modules.alerts.catalog import SNAPSHOT_PREFIX
from app.modules.alerts.catalog import AlertDefinition
from app.modules.alerts.checks import CHECKS
from app.modules.alerts.models import CheckContext
from app.modules.alerts.models import EffectiveSetting
from app.modules.alerts.models import Finding
from app.modules.monitoring.diagnostics.common import _query

logger = logging.getLogger(__name__)

# In-memory schedule: after a restart every enabled check runs once at the
# next cycle, then follows its tier.
_last_run: Dict[Tuple[str, str], datetime] = {}
BUSY = "busy"
INSTANCE_CONCURRENCY = 2


def classify(exc: MSSQLError) -> str:
    """A short, secret-free reason for the UI; never the raw driver message."""
    text = str(exc).lower()
    if "capacity exhausted" in text:
        return BUSY
    if "timeout" in text:
        return "Timed out"
    if "connection failed" in text:
        return "Connection failed"
    cause = str(exc.__cause__ or "").lower()
    if "permission" in cause or "denied" in cause:
        return "Missing permission"
    if any(marker in cause for marker in ("invalid object name", "invalid column", "could not find", "is not a recognized")):
        return "Not supported on this server"
    return "Query failed"


async def run_cycle(instances, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    rows = evaluation.index_settings(await alerts_repository.list_settings())
    states = {(state["instance_name"], state["alert_key"]): state for state in await alerts_repository.list_states()}
    slots = asyncio.Semaphore(INSTANCE_CONCURRENCY)

    async def guarded(name: str, connection_string: Optional[str]) -> None:
        async with slots:
            try:
                await _run_instance(name, connection_string, rows, states, now)
            except RepositoryUnavailable:
                logger.warning("Alerts: repository unavailable while evaluating %s", name)
            except Exception:
                logger.exception("Alerts: unexpected error evaluating %s", name)

    await asyncio.gather(*(guarded(i.name, i.mssql_connection_string) for i in instances), guarded(SELF_INSTANCE, None))


def _due(name: str, scope: str, rows, now: datetime) -> List[Tuple[AlertDefinition, EffectiveSetting]]:
    due = []
    for definition in CATALOG:
        if definition.scope != scope:
            continue
        setting = evaluation.effective_setting(definition, rows, name if scope == "instance" else "")
        if setting.enabled and evaluation.is_due(_last_run.get((name, definition.key)), setting.tier, now,
                                                 settings.COLLECTOR_INTERVAL_SECONDS):
            due.append((definition, setting))
    return due


async def _run_instance(name: str, connection_string: Optional[str], rows, states, now: datetime) -> None:
    due = _due(name, "data_eyes" if connection_string is None else "instance", rows, now)
    if not due:
        return
    run_query = None
    if connection_string is not None:
        run_query = lambda sql: _query(connection_string, sql)  # noqa: E731
        try:
            await run_query("SELECT 1 AS Reachable")
            unreachable = None
        except MSSQLError as exc:
            unreachable = classify(exc)
            if unreachable == BUSY:
                return  # retry next cycle rather than report a false outage
        for definition, setting in due:
            if definition.key == "sql_server_connection":
                finding = Finding("SQL Server", detail=f"unreachable: {unreachable}", floor="CRITICAL") if unreachable \
                    else Finding("SQL Server", detail="reachable")
                await _record_state(name, definition, setting, [finding], "", states, now)
                _last_run[(name, definition.key)] = now
        if unreachable:
            return
        due = [pair for pair in due if pair[0].key != "sql_server_connection"]

    memory = await alerts_repository.load_memory(name)
    cache: Dict[str, object] = {}
    for definition, setting in due:
        saved = memory.get(definition.key) or {}
        ctx = CheckContext(name, connection_string, setting, dict(saved), now, run_query, cache)
        error = ""
        try:
            result = await CHECKS[definition.key](ctx)
        except MSSQLError as exc:
            error = classify(exc)
            if error == BUSY:
                continue
            result = None
        except RepositoryUnavailable:
            raise
        except Exception:
            logger.exception("Alerts: check %s failed for %s", definition.key, name)
            result, error = None, "Check failed"
        if definition.kind == "state":
            await _record_state(name, definition, setting, result, error, states, now)
        else:
            await _record_events(name, definition, setting, result, error, states, now)
        # Watermarks only advance after a successful check, so a failed read
        # is retried instead of silently skipping events.
        if result is not None and ctx.memory != saved:
            await alerts_repository.save_memory(name, definition.key, ctx.memory)
        _last_run[(name, definition.key)] = now


def _changed_at(previous: Optional[dict], severity: str, now: datetime) -> datetime:
    return now if previous is None or previous["severity"] != severity else previous["changed_at"]


async def _record_state(name, definition, setting, findings, error, states, now) -> None:
    if findings is None:
        observed, metric, detail = "UNKNOWN", None, ""
    else:
        observed, metric, detail = evaluation.summarize(findings, definition, setting)
    previous = states.get((name, definition.key))
    severity, streak = evaluation.confirm(previous, observed, setting.confirm_samples)
    state = {"severity": severity, "observed_severity": observed, "streak": streak, "metric_value": metric,
             "detail": detail, "status": "error" if error else "ok", "status_message": error,
             "checked_at": now, "changed_at": _changed_at(previous, severity, now)}
    await alerts_repository.save_state(name, definition.key, state)
    states[(name, definition.key)] = state
    await monitoring_repository.insert_category_snapshot(name, SNAPSHOT_PREFIX + definition.key, severity, metric)


async def _record_events(name, definition, setting, occurrences, error, states, now) -> None:
    rows = evaluation.event_rows(occurrences or [], definition, setting)
    inserted = await alerts_repository.insert_events(name, definition.key, rows)
    severity = evaluation.worst(row["severity"] for row in inserted)
    previous = states.get((name, definition.key))
    state = {"severity": severity, "observed_severity": severity, "streak": 1,
             "metric_value": float(len(inserted)) if inserted else None,
             "detail": "\n".join(row["detail"] for row in inserted[:5]), "status": "error" if error else "ok",
             "status_message": error, "checked_at": now, "changed_at": _changed_at(previous, severity, now)}
    await alerts_repository.save_state(name, definition.key, state)
    states[(name, definition.key)] = state


def forget(alert_key: str, instance_name: Optional[str] = None) -> None:
    """Make a re-enabled or retuned alert run at the next cycle."""
    for key in [key for key in _last_run if key[1] == alert_key and (instance_name is None or key[0] == instance_name)]:
        del _last_run[key]
