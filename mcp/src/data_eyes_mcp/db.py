"""Run one fixed, read-only statement against a fleet instance.

Every call opens a connection with the instance's scoped login, runs in a worker
thread with a bounded slot, cancels the ODBC cursor on timeout, and caps rows,
cell length, and total bytes. Transactions are never committed.
"""

import asyncio
import logging
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import pyodbc

from data_eyes_mcp.config import Instance, credentials, resolve_instance, settings

logger = logging.getLogger(__name__)
TRUNCATED = "…[TRUNCATED_UNTRUSTED_DATA]"
_slots: Optional[asyncio.Semaphore] = None


class DatabaseError(Exception):
    pass


@dataclass
class Result:
    columns: List[str] = field(default_factory=list)
    rows: List[Tuple[Any, ...]] = field(default_factory=list)
    truncated: bool = False


def _odbc_pairs(connection_string: str) -> List[Tuple[str, str]]:
    """Split an ODBC connection string, honouring {braced;values} and }} escapes."""
    pairs, key, value, in_key, braced, i = [], "", "", True, False, 0
    while i < len(connection_string):
        char = connection_string[i]
        if in_key:
            if char == "=":
                in_key = False
            elif char != ";":
                key += char
        elif braced:
            value += char
            if char == "}" and connection_string[i + 1:i + 2] == "}":
                value += "}"
                i += 1
            elif char == "}":
                braced = False
        elif char == "{" and not value.strip():
            braced, value = True, char
        elif char == ";":
            pairs.append((key.strip(), value.strip()))
            key, value, in_key = "", "", True
        else:
            value += char
        i += 1
    if key.strip():
        pairs.append((key.strip(), value.strip()))
    return pairs


def _quote(value: str) -> str:
    if any(c in value for c in ";{}") or value != value.strip():
        return "{" + value.replace("}", "}}") + "}"
    return value


def connection_string(instance: Instance, database: Optional[str] = None) -> str:
    """The instance's base string with its scoped login, database, and APP name applied."""
    user, password, trusted = credentials(instance)
    database = database or settings.DEFAULT_DATABASE
    replaced = {"uid", "user id", "pwd", "password", "trusted_connection"}
    if database:
        replaced |= {"database", "initial catalog"}
    pairs = [(k, v) for k, v in _odbc_pairs(instance.mssql_connection_string) if k.lower() not in replaced]
    if trusted:
        pairs.append(("Trusted_Connection", "yes"))
    else:
        pairs += [("UID", _quote(user or "")), ("PWD", _quote(password or ""))]
    if database:
        pairs.append(("Database", _quote(database)))
    if settings.MSSQL_APPLICATION_NAME and not any(k.lower() == "app" for k, _ in pairs):
        pairs.append(("APP", _quote(settings.MSSQL_APPLICATION_NAME)))
    return ";".join(f"{k}={v}" for k, v in pairs) + ";"


@contextmanager
def _connect(instance: Instance, database: Optional[str]):
    try:
        conn = pyodbc.connect(connection_string(instance, database), autocommit=False,
                              timeout=settings.MSSQL_CONNECTION_TIMEOUT)
    except pyodbc.Error as exc:
        logger.warning("Connection failed instance=%s sqlstate=%s", instance.name, exc.args[0] if exc.args else "")
        raise DatabaseError(f"Could not connect to instance {instance.name!r}") from None
    try:
        # SQL Server expects UTF-16LE statement text; decode narrow data as UTF-8.
        conn.setencoding(encoding="utf-16-le")
        conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16-le")
        conn.setdecoding(pyodbc.SQL_WMETADATA, encoding="utf-16-le")
        yield conn
    finally:
        conn.close()  # uncommitted work is rolled back


def _cell(value: Any) -> Any:
    if isinstance(value, str) and len(value) > settings.MAX_CELL_LENGTH:
        return value[: settings.MAX_CELL_LENGTH] + TRUNCATED
    if isinstance(value, (bytes, bytearray)):
        return "<binary>"
    return value


def _fetch(cursor, max_rows: int) -> Result:
    columns = [column[0] for column in cursor.description or []]
    rows: List[Tuple[Any, ...]] = []
    size = 0
    while batch := cursor.fetchmany(1000):
        for raw in batch:
            row = tuple(_cell(value) for value in raw)
            size += sum(len(str(value)) for value in row)
            if len(rows) >= max_rows or size > settings.MAX_RESPONSE_BYTES:
                return Result(columns, rows, truncated=True)
            rows.append(row)
    return Result(columns, rows)


def _sql_error(exc: pyodbc.Error) -> str:
    """SQL Server's message without the driver prefix, e.g. "Invalid object name 'x'. (208)"."""
    message = str(exc.args[1] if len(exc.args) > 1 else exc)
    return re.sub(r"^(\[[^\]]*\])+", "", message).replace(" (SQLExecDirectW)", "").strip()


async def run(instance: Optional[str], sql: str, params: Sequence[Any] = (),
              database: Optional[str] = None, max_rows: Optional[int] = None) -> Result:
    """Execute one statement and return capped rows. Raises DatabaseError."""
    global _slots
    target = resolve_instance(instance)
    max_rows = min(max_rows or settings.MAX_ROWS_PER_QUERY, settings.MAX_ROWS_PER_QUERY)
    timeout = settings.MSSQL_QUERY_TIMEOUT
    cancelled = threading.Event()
    cursors: list = []

    def execute() -> Result:
        with _connect(target, database) as conn:
            conn.timeout = timeout
            cursor = conn.cursor()
            cursors.append(cursor)
            try:
                if cancelled.is_set():
                    return Result()
                cursor.execute(sql, *params)
                return _fetch(cursor, max_rows)
            except pyodbc.Error as exc:
                raise DatabaseError(_sql_error(exc)) from None
            finally:
                cursor.close()

    if _slots is None:
        _slots = asyncio.Semaphore(settings.MAX_CONCURRENT_QUERIES)
    slots = _slots
    try:
        await asyncio.wait_for(slots.acquire(), timeout=1)
    except asyncio.TimeoutError:
        raise DatabaseError("Query capacity exhausted; retry shortly") from None
    # The slot is held until the worker thread really finishes, even after a timeout.
    task = asyncio.ensure_future(asyncio.to_thread(execute))
    task.add_done_callback(lambda done: (slots.release(), done.cancelled() or done.exception()))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout + 1)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        cancelled.set()
        for cursor in cursors:
            asyncio.ensure_future(asyncio.to_thread(cursor.cancel)).add_done_callback(
                lambda done: done.cancelled() or done.exception())
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise DatabaseError(f"Query exceeded {timeout}s timeout") from None
