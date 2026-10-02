"""
Direct SQL Server client for the dashboard backend.

Ports the connection/execution pattern from mcp/src/data_eyes_mcp/db.py, but
without that module's per-request credential override machinery — this
backend holds one connection string per registered instance (see
app/config.py's InstanceConfig, and app/repository.py's instance table once
Phase 2 lands) and never needs to swap identity mid-request the way a shared
MCP server serving multiple remote clients does.

Replaces app/mcp_client.py: the dashboard used to reach every monitored SQL
Server through its own data-eyes-mcp server over the MCP protocol, for every
page render. That was needless overhead for a trusted backend doing routine
reads — MCP's tool-calling/policy-gate machinery earns its keep for an LLM
agent, not here. See app/diagnostics.py for the queries that use this client.

Runs each query in a thread (pyodbc is synchronous) so the event loop stays
free for other requests — same reasoning as the MCP server's db.py.
"""

import asyncio
import logging
import threading
from .config import settings
from .connection_policy import parse_connection_string
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pyodbc

logger = logging.getLogger(__name__)

pyodbc.pooling = True

DEFAULT_QUERY_TIMEOUT = 30
DEFAULT_MAX_ROWS = 50000
MSSQL_ENCODING = "utf-8"
MSSQL_WIDE_ENCODING = "utf-16-le"


class MSSQLError(Exception):
    """Raised for any connection/query failure talking to a monitored SQL Server."""


@dataclass
class QueryResult:
    columns: List[str] = field(default_factory=list)
    rows: List[Tuple[Any, ...]] = field(default_factory=list)
    truncated: bool = False


def _quote_odbc_value(value: str) -> str:
    if value and (";" in value or "{" in value or "}" in value or value.strip() != value):
        return "{" + value.replace("}", "}}") + "}"
    return value


def _apply_database(connection_string: str, database: Optional[str]) -> str:
    """Override the initial catalog (Database=/Initial Catalog=) in a
    connection string when `database` is given, so tab/diagnostic queries
    that target a specific database don't rely on the login's default.
    Leaves the base string untouched when database is None."""
    if not database:
        return connection_string
    options = parse_connection_string(connection_string)
    options["database"] = database
    return ";".join(f"{key}={_quote_odbc_value(value)}" for key, value in options.items()) + ";"



@contextmanager
def _get_connection(connection_string: str, database: Optional[str] = None, connect_timeout: int = 30):
    conn = None
    try:
        conn = pyodbc.connect(
            _apply_database(connection_string, database),
            autocommit=False,
            timeout=connect_timeout,
        )
        # Same encoding setup as mcp/'s db.py — SQL Server expects query/param
        # text as UTF-16LE; result decoding is set explicitly since pyodbc's
        # platform defaults can otherwise garble VARCHAR/NVARCHAR values.
        conn.setencoding(encoding=MSSQL_WIDE_ENCODING)
        conn.setdecoding(pyodbc.SQL_CHAR, encoding=MSSQL_ENCODING)
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding=MSSQL_WIDE_ENCODING)
        conn.setdecoding(pyodbc.SQL_WMETADATA, encoding=MSSQL_WIDE_ENCODING)
        yield conn
    except pyodbc.Error as e:
        raise MSSQLError("SQL Server connection failed; check server and credentials") from e
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.warning("Error closing SQL Server connection", exc_info=True)


def _fetch_rows(cursor, max_rows: int, batch_size: int = 100) -> Tuple[List[Tuple[Any, ...]], bool]:
    rows = []
    size = 0
    truncated = False
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        for raw in batch:
            if len(rows) >= max_rows:
                return rows, True
            row = []
            for value in raw:
                if isinstance(value, (str, bytes, bytearray)) and len(value) > settings.SQL_MAX_CELL_LENGTH:
                    value = value[:settings.SQL_MAX_CELL_LENGTH]
                    truncated = True
                row.append(value)
            cost = sum(len(str(value).encode("utf-8")) for value in row)
            if size + cost > settings.SQL_MAX_RESPONSE_BYTES:
                return rows, True
            size += cost
            rows.append(tuple(row))
    return rows, truncated


# Interactive requests (fleet rollup, tabs) and background collectors draw from
# separate pools so the 3s activity sampler can't starve user-facing queries.
# The collector sets the lane once per loop; asyncio.gather children inherit it.
query_lane: ContextVar[str] = ContextVar("query_lane", default="interactive")
_query_slots: Dict[str, asyncio.Semaphore] = {}


async def execute_query(connection_string: str, sql: str, database: Optional[str] = None,
                        timeout: int = DEFAULT_QUERY_TIMEOUT, max_rows: int = DEFAULT_MAX_ROWS) -> QueryResult:
    if not 1 <= timeout <= DEFAULT_QUERY_TIMEOUT or not 1 <= max_rows <= DEFAULT_MAX_ROWS:
        raise MSSQLError("Query limits exceed server limits")
    lane = query_lane.get()
    slots = _query_slots.get(lane)
    if slots is None:
        size = settings.SQL_MAX_BACKGROUND_QUERIES if lane == "background" else settings.SQL_MAX_CONCURRENT_QUERIES
        slots = _query_slots[lane] = asyncio.Semaphore(size)
    try:
        await asyncio.wait_for(slots.acquire(), timeout=settings.SQL_QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise MSSQLError("SQL query capacity exhausted; retry shortly") from None
    cancelled = threading.Event()
    cursors = []

    def run():
        with _get_connection(connection_string, database, connect_timeout=min(timeout, 10)) as conn:
            # pyodbc statement timeout belongs to the connection, not Cursor.
            conn.timeout = timeout
            cursor = conn.cursor()
            cursors.append(cursor)
            try:
                if cancelled.is_set():
                    return QueryResult()
                cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                if not columns:
                    return QueryResult()
                rows, truncated = _fetch_rows(cursor, max_rows)
                return QueryResult(columns=columns, rows=rows, truncated=truncated)
            except pyodbc.Error as exc:
                raise MSSQLError("SQL diagnostic query failed") from exc
            finally:
                cursor.close()

    def cancel():
        if cursors:
            try:
                cursors[0].cancel()
            except Exception:
                pass  # It may already have closed.

    task = asyncio.create_task(asyncio.to_thread(run))
    def finished(task):
        slots.release()  # Keep capacity reserved until the ODBC thread exits.
        if not task.cancelled():
            task.exception()
    task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout + 1)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        cancelled.set()
        cancel_task = asyncio.create_task(asyncio.to_thread(cancel))
        cancel_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise MSSQLError(f"Query exceeded {timeout}s timeout") from None
    except MSSQLError:
        raise
    except Exception as exc:
        raise MSSQLError("SQL diagnostic failed") from exc
