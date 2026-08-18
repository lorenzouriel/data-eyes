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
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

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
    drop = {"database", "initial catalog"}
    kept = []
    for part in connection_string.split(";"):
        if not part.strip():
            continue
        key = part.split("=", 1)[0].strip().lower()
        if key in drop:
            continue
        kept.append(part.strip())
    kept.append(f"Database={_quote_odbc_value(database)}")
    return ";".join(kept) + ";"


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
        raise MSSQLError(f"Failed to connect: {e}") from e
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.warning("Error closing SQL Server connection", exc_info=True)


def _fetch_rows(cursor, max_rows: int, batch_size: int = 1000) -> Tuple[List[Tuple[Any, ...]], bool]:
    rows: List[Tuple[Any, ...]] = []
    truncated = False
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        rows.extend(batch)
        if len(rows) > max_rows:
            rows = rows[:max_rows]
            truncated = True
            break
    return rows, truncated


async def execute_query(
    connection_string: str,
    sql: str,
    database: Optional[str] = None,
    timeout: int = DEFAULT_QUERY_TIMEOUT,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> QueryResult:
    """Execute a read-only diagnostic query against one instance's SQL Server.

    Every query app/diagnostics.py builds is a fixed, parameter-free SELECT —
    there's no policy-gate/write-mode concept here, unlike mcp/'s general-
    purpose execute_sql tool, which has to defend against arbitrary LLM-issued
    SQL. This client only ever runs the queries diagnostics.py builds.
    """

    def _sync_execute() -> QueryResult:
        with _get_connection(connection_string, database) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                if not columns:
                    return QueryResult()
                rows, truncated = _fetch_rows(cursor, max_rows)
                return QueryResult(columns=columns, rows=rows, truncated=truncated)
            except pyodbc.Error as e:
                raise MSSQLError(f"Query failed: {e}") from e
            finally:
                try:
                    cursor.close()
                except Exception:
                    logger.warning("Error closing cursor", exc_info=True)

    try:
        coro = asyncio.to_thread(_sync_execute)
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise MSSQLError(f"Query exceeded {timeout}s timeout") from None
    except MSSQLError:
        raise
    except Exception as e:
        raise MSSQLError(f"Unexpected error: {e}") from e
