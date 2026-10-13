"""
SQL Server client: fixed read-only queries with time, size and concurrency limits.

pyodbc is synchronous, so each query runs in a worker thread and the event
loop stays free. Queries are grouped into lanes: the fast metric cycle and
the slower alert checks draw from separate slot pools, so a long check never
delays the 30-second metrics.
"""

import asyncio
import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, List

import pyodbc

from app.config import settings

LOG = logging.getLogger(__name__)

# Takes effect only with Pooling=Yes in odbcinst.ini (set in the Dockerfile).
pyodbc.pooling = True

QUERY_TIMEOUT_SECONDS = 30


class MSSQLError(Exception):
    """Any connection or query failure talking to a monitored SQL Server."""


class QueryLimitExceeded(MSSQLError):
    """The query ran into its time or size ceiling. Unlike a connection or
    permission failure, the server already did that work, so retrying at once
    repeats the cost."""


_lane: ContextVar[str] = ContextVar("query_lane", default="metrics")
_slots: Dict[str, asyncio.Semaphore] = {}


@contextmanager
def query_lane(name: str):
    """Run the queries issued inside this block in the named lane."""
    token = _lane.set(name)
    try:
        yield
    finally:
        _lane.reset(token)


def _quote_odbc_value(value: str) -> str:
    if value and (";" in value or "{" in value or "}" in value or value.strip() != value):
        return "{" + value.replace("}", "}}") + "}"
    return value


def _with_application_name(connection_string: str) -> str:
    """Tag sessions with an application name (APP_NAME(), program_name in
    sys.dm_exec_sessions) so DBAs can identify the collector and classify it
    with Resource Governor. An APP= already in the connection string wins."""
    keys = {part.split("=", 1)[0].strip().lower() for part in connection_string.split(";") if "=" in part}
    if "app" in keys or not settings.SQL_APPLICATION_NAME:
        return connection_string
    return connection_string.rstrip().rstrip(";") + ";APP=" + _quote_odbc_value(settings.SQL_APPLICATION_NAME) + ";"


def _value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _run(connection_string: str, sql: str, timeout: int, cursors: list, cancelled: threading.Event) -> List[Dict[str, Any]]:
    try:
        conn = pyodbc.connect(_with_application_name(connection_string), autocommit=False, timeout=min(timeout, 10))
    except pyodbc.Error as exc:
        raise MSSQLError("SQL Server connection failed; check server and credentials") from exc
    try:
        # SQL Server expects query text as UTF-16LE; decoding is explicit
        # because pyodbc's platform defaults can garble VARCHAR/NVARCHAR.
        conn.setencoding(encoding="utf-16-le")
        conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16-le")
        conn.setdecoding(pyodbc.SQL_WMETADATA, encoding="utf-16-le")
        conn.timeout = timeout  # statement timeout; pyodbc sets it on the connection
        cursor = conn.cursor()
        cursors.append(cursor)
        if cancelled.is_set():
            return []
        try:
            cursor.execute(sql)
            # Multi-statement batches (temp tables, INSERT...EXEC) can emit
            # row counts before the final SELECT.
            while cursor.description is None and cursor.nextset():
                pass
            if not cursor.description:
                return []
            columns = [column[0] for column in cursor.description]
            rows, size = [], 0
            while batch := cursor.fetchmany(100):
                for raw in batch:
                    if any(isinstance(v, (str, bytes, bytearray)) and len(v) > settings.SQL_MAX_CELL_LENGTH for v in raw):
                        raise QueryLimitExceeded("Diagnostic result exceeded collection limits")
                    size += sum(len(str(v).encode("utf-8")) for v in raw)
                    if size > settings.SQL_MAX_RESPONSE_BYTES:
                        raise QueryLimitExceeded("Diagnostic result exceeded collection limits")
                    rows.append({column: _value(v) for column, v in zip(columns, raw)})
            return rows
        except pyodbc.Error as exc:
            # HYT00 is the ODBC statement timeout set above.
            if exc.args and exc.args[0] == "HYT00":
                raise QueryLimitExceeded(f"Query exceeded {timeout}s timeout") from exc
            raise MSSQLError("SQL diagnostic query failed") from exc
        finally:
            cursor.close()
    finally:
        try:
            conn.close()
        except Exception:
            LOG.warning("Error closing SQL Server connection")


async def query(connection_string: str, sql: str, timeout: int = QUERY_TIMEOUT_SECONDS) -> List[Dict[str, Any]]:
    """Run one fixed statement and return its rows as dicts."""
    lane = _lane.get()
    checks = lane == "checks"
    slots = _slots.get(lane)
    if slots is None:
        slots = _slots[lane] = asyncio.Semaphore(settings.SQL_MAX_BACKGROUND_QUERIES if checks else settings.SQL_MAX_CONCURRENT_QUERIES)
    # Every instance's checks share the check slots, so they queue rather
    # than fail fast; failing would report a false UNKNOWN.
    queue_timeout = settings.SQL_BACKGROUND_QUEUE_TIMEOUT_SECONDS if checks else settings.SQL_QUEUE_TIMEOUT_SECONDS
    try:
        await asyncio.wait_for(slots.acquire(), timeout=queue_timeout)
    except asyncio.TimeoutError:
        raise MSSQLError("SQL query capacity exhausted; retry shortly") from None

    cursors: list = []
    cancelled = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(_run, connection_string, sql, timeout, cursors, cancelled))

    def finished(task):
        slots.release()  # Keep capacity reserved until the ODBC thread exits.
        if not task.cancelled():
            task.exception()

    task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout + 1)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        cancelled.set()
        if cursors:
            with_cancel = asyncio.create_task(asyncio.to_thread(cursors[0].cancel))
            with_cancel.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise QueryLimitExceeded(f"Query exceeded {timeout}s timeout") from None
    except MSSQLError:
        raise
    except Exception as exc:
        raise MSSQLError("SQL diagnostic failed") from exc
