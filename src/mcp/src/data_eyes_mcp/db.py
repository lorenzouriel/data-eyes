"""
Database layer for Data Eyes MCP Server.

Provides connection pooling, query execution with timeouts, and safe result handling.
Uses pyodbc with connection pooling and thread-safe execution via asyncio.to_thread.
"""

import asyncio
import logging
import os
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pyodbc

from .config import get_instance, load_instances, settings
from .security import (
    audit,
    authorize,
    enforce_rate_limit,
    reset_instance,
    reset_principal,
    set_instance,
    set_principal,
)

logger = logging.getLogger(__name__)

# Per-request SQL credential override (set from MCP request headers). When set,
# it takes precedence over the server's own MSSQL_USER/MSSQL_PASSWORD settings for
# the duration of one request, letting a remote client authenticate as its own SQL
# login. Copied into worker threads by asyncio.to_thread, so it reaches the sync
# DB code. None means "use server defaults".
_request_credentials: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "mssql_request_credentials", default=None
)


@contextmanager
def request_credentials(user: Optional[str] = None, password: Optional[str] = None,
                        trusted: Optional[bool] = None, instance: Optional[str] = None,
                        principal: Optional[str] = None):
    """Bind per-request SQL credentials and fleet instance for one call.

    A no-op when all three are unset, so callers can wrap unconditionally.
    """
    if (user or password or trusted is not None) and not settings.ALLOW_REQUEST_CREDENTIALS:
        raise PermissionError("per-request SQL credentials are disabled")
    token = _request_credentials.set(
        {"user": user, "password": password, "trusted": trusted, "instance": instance}
    )
    principal_token = set_principal(principal)
    instance_token = set_instance(instance or settings.DEFAULT_INSTANCE)
    try:
        yield
    finally:
        reset_instance(instance_token)
        reset_principal(principal_token)
        _request_credentials.reset(token)


def _effective_credentials() -> Tuple[Optional[str], Optional[str], Optional[bool]]:
    """Return (user, password, trusted): per-request override if set, else settings."""
    req = _request_credentials.get()
    if req is not None and (req.get("user") or req.get("password") or req.get("trusted") is not None):
        return req.get("user"), req.get("password"), req.get("trusted")
    configured = get_instance(_effective_instance())
    if configured and configured.credential_env_prefix:
        prefix = configured.credential_env_prefix
        user = os.getenv(f"{prefix}_MSSQL_USER")
        password = os.getenv(f"{prefix}_MSSQL_PASSWORD")
        trusted_value = os.getenv(f"{prefix}_MSSQL_TRUSTED_CONNECTION")
        trusted = None if trusted_value is None else trusted_value.lower() in ("1", "true", "yes", "on")
        if user or password or trusted is not None:
            return user, password, trusted
    return settings.MSSQL_USER, settings.MSSQL_PASSWORD, settings.MSSQL_TRUSTED_CONNECTION


def _effective_instance() -> Optional[str]:
    req = _request_credentials.get()
    return req.get("instance") if req is not None else None


def resolve_database(database: Optional[str] = None) -> Optional[str]:
    """Resolve the real initial catalog without exposing the connection string."""
    if database:
        return database
    if settings.DEFAULT_DATABASE:
        return settings.DEFAULT_DATABASE
    instance = get_instance(_effective_instance())
    base = instance.mssql_connection_string if instance else settings.MSSQL_CONNECTION_STRING
    if not base:
        return None
    match = re.search(r"(?:^|;)\s*(?:Database|Initial Catalog)\s*=\s*([^;]+)", base, re.I)
    return match.group(1).strip().strip("{}") if match else None


@dataclass
class QueryResult:
    """Result of a query execution.

    Attributes:
        columns: Column names (empty for statements with no result set).
        rows: Result rows, capped at max_rows.
        truncated: True if more rows were available than max_rows.
        rowcount: Affected-row count for write statements; -1 when not applicable.
    """
    columns: List[str] = field(default_factory=list)
    rows: List[Tuple[Any, ...]] = field(default_factory=list)
    truncated: bool = False
    rowcount: int = -1
    response_bytes: int = 0

# Enable ODBC connection pooling for better resource management
pyodbc.pooling = True
_query_semaphore: Optional[asyncio.Semaphore] = None


def _get_query_semaphore() -> asyncio.Semaphore:
    global _query_semaphore
    if _query_semaphore is None:
        _query_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_QUERIES)
    return _query_semaphore


class DatabaseError(Exception):
    """Base database error."""
    pass


class QueryTimeoutError(DatabaseError):
    """Query execution exceeded timeout."""
    pass


class ConnectionError(DatabaseError):
    """Database connection error."""
    pass


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and len(value) > settings.MAX_CELL_LENGTH:
        return value[: settings.MAX_CELL_LENGTH] + "…[TRUNCATED_UNTRUSTED_DATA]"
    if isinstance(value, (bytes, bytearray)):
        return b"<binary>"
    return value


def _fetch_rows(cursor, max_rows: int, batch_size: int = 1000) -> Tuple[List[Tuple[Any, ...]], bool, int]:
    """Fetch up to max_rows rows from a cursor, reporting truncation.

    Allows the row count to exceed max_rows before trimming so that a result
    of exactly max_rows rows is not mislabelled as truncated.

    Returns (rows, truncated).
    """
    rows: List[Tuple[Any, ...]] = []
    truncated = False
    response_bytes = 0
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        for raw_row in batch:
            row = tuple(_safe_cell(value) for value in raw_row)
            row_bytes = sum(len(str(value).encode("utf-8", errors="replace")) for value in row)
            if response_bytes + row_bytes > settings.MAX_RESPONSE_BYTES or len(rows) >= max_rows:
                truncated = True
                return rows, truncated, response_bytes
            rows.append(row)
            response_bytes += row_bytes
        if len(rows) > max_rows:
            rows = rows[:max_rows]
            truncated = True
            break
    return rows, truncated, response_bytes


def _quote_odbc_value(value: str) -> str:
    """Wrap an ODBC connection value in braces if it contains special chars."""
    if value and (";" in value or "{" in value or "}" in value or value.strip() != value):
        return "{" + value.replace("}", "}}") + "}"
    return value


def build_connection_string(database: Optional[str] = None) -> str:  # noqa: C901
    """Build the effective connection string, applying optional overrides.

    Credentials come from the per-request override if one is bound (see
    request_credentials), otherwise from MSSQL_USER / MSSQL_PASSWORD /
    MSSQL_TRUSTED_CONNECTION. They take precedence over UID/PWD embedded in
    MSSQL_CONNECTION_STRING.

    The initial catalog comes from the `database` argument if given, else from
    DEFAULT_DATABASE; when set it overrides any Database/Initial Catalog in the
    base string, so unqualified names resolve in that database. Only the keys
    being overridden are replaced; everything else is preserved.
    """
    requested_instance = _effective_instance()
    configured_instance = get_instance(requested_instance)
    if configured_instance is not None:
        base = configured_instance.mssql_connection_string
    elif load_instances():
        available = ", ".join(instance.name for instance in load_instances())
        raise ConnectionError(f"Select an instance; configured instances: {available}")
    elif settings.MSSQL_CONNECTION_STRING:
        base = settings.MSSQL_CONNECTION_STRING
    else:
        available = ", ".join(instance.name for instance in load_instances())
        raise ConnectionError(
            "An instance must be selected; configured instances: " + (available or "none")
        )
    user, password, trusted = _effective_credentials()
    db = database or settings.DEFAULT_DATABASE

    # Nothing to override -> use the connection string as-is.
    if not user and not password and trusted is None and not db:
        return base

    # Determine which keys to drop from the base string.
    drop = set()
    if trusted is True:
        drop |= {"uid", "pwd", "user id", "password", "trusted_connection"}
    elif trusted is False:
        drop |= {"trusted_connection"}
    if user:
        drop |= {"uid", "user id"}
    if password:
        drop |= {"pwd", "password"}
    if db:
        drop |= {"database", "initial catalog"}

    kept = []
    for part in base.split(";"):
        if not part.strip():
            continue
        key = part.split("=", 1)[0].strip().lower()
        if key in drop:
            continue
        kept.append(part.strip())

    if trusted is True:
        kept.append("Trusted_Connection=yes")
    else:
        if user:
            kept.append(f"UID={_quote_odbc_value(user)}")
        if password:
            kept.append(f"PWD={_quote_odbc_value(password)}")
    if db:
        kept.append(f"Database={_quote_odbc_value(db)}")

    return ";".join(kept) + ";"


@contextmanager
def get_connection(database: Optional[str] = None):
    """
    Context manager for database connections with automatic cleanup.
    Uses connection pooling for efficiency. `database` (or DEFAULT_DATABASE) sets
    the initial catalog for this connection.
    """
    conn = None
    try:
        conn = pyodbc.connect(
            build_connection_string(database),
            autocommit=False,
            timeout=settings.MSSQL_CONNECTION_TIMEOUT,
        )
        # Configure character encoding so non-ASCII data (e.g. accented text) is
        # sent and decoded correctly. SQL Server expects the query/parameter text
        # as UTF-16LE (setencoding); sending UTF-8 corrupts non-ASCII literals in
        # queries. Result decoding is set explicitly too, since pyodbc's platform
        # defaults can otherwise garble VARCHAR/NVARCHAR values.
        conn.setencoding(encoding=settings.MSSQL_WIDE_ENCODING)
        conn.setdecoding(pyodbc.SQL_CHAR, encoding=settings.MSSQL_ENCODING)
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding=settings.MSSQL_WIDE_ENCODING)
        conn.setdecoding(pyodbc.SQL_WMETADATA, encoding=settings.MSSQL_WIDE_ENCODING)
        yield conn
    except pyodbc.Error as e:
        logger.exception("Database connection error: %s", e)
        raise ConnectionError("Failed to connect to database") from e
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning("Error closing connection: %s", e)


async def execute_query(  # noqa: C901
    sql: str,
    params: Tuple = (),
    timeout: Optional[int] = None,
    max_rows: Optional[int] = None,
    database: Optional[str] = None,
) -> QueryResult:
    """
    Execute a SQL statement asynchronously.

    Runs in a thread to avoid blocking the event loop. Handles both queries that
    return a result set (SELECT) and statements that do not (INSERT/UPDATE/DELETE).

    Args:
        sql: SQL statement to execute
        params: Query parameters (for parameterized queries)
        timeout: Query timeout in seconds (defaults to MSSQL_QUERY_TIMEOUT)
        max_rows: Maximum rows to return (defaults to MAX_ROWS_PER_QUERY)
        database: Initial catalog for this call (defaults to DEFAULT_DATABASE /
            the login's default); fully-qualified names still work regardless.

    Returns:
        QueryResult with columns, rows, truncated flag and affected rowcount.

    Raises:
        QueryTimeoutError: If query exceeds timeout
        DatabaseError: For other database errors
    """
    timeout = settings.MSSQL_QUERY_TIMEOUT if timeout is None else timeout
    max_rows = settings.MAX_ROWS_PER_QUERY if max_rows is None else max_rows
    if timeout < 1 or timeout > settings.MSSQL_QUERY_TIMEOUT:
        raise DatabaseError(f"timeout must be between 1 and {settings.MSSQL_QUERY_TIMEOUT} seconds")
    if max_rows < 1 or max_rows > settings.MAX_ROWS_PER_QUERY:
        raise DatabaseError(f"max_rows must be between 1 and {settings.MAX_ROWS_PER_QUERY}")

    enforce_rate_limit()
    configured_instance = get_instance(_effective_instance() or settings.DEFAULT_INSTANCE)
    selected_instance = configured_instance.name if configured_instance else _effective_instance()
    effective_database = resolve_database(database)
    authorize(instance=selected_instance, database=effective_database)
    started = __import__("time").monotonic()
    cursor_holder: Dict[str, Any] = {}
    cancelled = threading.Event()

    def _sync_execute() -> QueryResult:
        """Synchronous query execution in thread."""
        with get_connection(database) as conn:
            conn.timeout = timeout
            cursor = conn.cursor()
            cursor_holder["cursor"] = cursor
            try:
                if cancelled.is_set():
                    return QueryResult()
                cursor.execute(sql, params)
                # Extract column names from cursor description
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                if columns:
                    # Fetch rows with batch processing for memory efficiency,
                    # flagging truncation when more than max_rows are available.
                    rows, truncated, response_bytes = _fetch_rows(cursor, max_rows)
                    return QueryResult(
                        columns=columns,
                        rows=rows,
                        truncated=truncated,
                        response_bytes=response_bytes,
                    )
                else:
                    # No result set: write statement (INSERT/UPDATE/DELETE) or USE.
                    # Capture affected rows and commit the transaction.
                    rowcount = cursor.rowcount
                    conn.commit()
                    return QueryResult(columns=[], rows=[], rowcount=rowcount)
            except pyodbc.Error as e:
                logger.exception("Query execution error: %s", e)
                raise DatabaseError("Query execution failed") from e
            finally:
                cursor_holder.pop("cursor", None)
                try:
                    cursor.close()
                except Exception as e:
                    logger.warning("Error closing cursor: %s", e)

    # Execute in a bounded worker slot with both driver-level and cooperative
    # cancellation. The queue wait is intentionally outside the DB timeout.
    semaphore = _get_query_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=1)
    except asyncio.TimeoutError:
        raise DatabaseError("Query capacity exhausted; retry shortly") from None
    try:
        task = asyncio.create_task(asyncio.to_thread(_sync_execute))
        def finished(task):
            semaphore.release()
            if not task.cancelled():
                task.exception()
        task.add_done_callback(finished)
        result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout + 1)
        audit(
            "allow",
            "query_completed",
            database=effective_database,
            duration_ms=round((__import__("time").monotonic() - started) * 1000, 2),
            rows=len(result.rows),
            response_bytes=result.response_bytes,
        )
        return result
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        cancelled.set()
        cursor = cursor_holder.get("cursor")
        if cursor is not None:
            async def cancel_cursor():
                try:
                    await asyncio.to_thread(cursor.cancel)
                except Exception:
                    pass
            cancellation = asyncio.create_task(cancel_cursor())
            cancellation.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        if isinstance(exc, asyncio.CancelledError):
            raise
        logger.error("Query timeout after %d seconds", timeout)
        audit("deny", "query_timeout_cancelled", database=effective_database, duration_ms=timeout * 1000)
        raise QueryTimeoutError(f"Query execution exceeded {timeout}s timeout") from None
    except Exception as e:
        if isinstance(e, (DatabaseError, QueryTimeoutError)):
            audit(
                "deny",
                "query_error",
                database=effective_database,
                duration_ms=round((__import__("time").monotonic() - started) * 1000, 2),
                error_type=type(e).__name__,
            )
            raise
        logger.exception("Unexpected error during query execution: %s", e)
        audit(
            "deny",
            "query_error",
            database=effective_database,
            duration_ms=round((__import__("time").monotonic() - started) * 1000, 2),
            error_type=type(e).__name__,
        )
        raise DatabaseError("Unexpected database error") from e


async def execute_schema_query(sql: str, timeout: Optional[int] = None,
                               database: Optional[str] = None) -> QueryResult:
    """
    Execute a schema/metadata query with relaxed row limits.
    Used for list_tables, list_schemas, schema_discovery. `database` targets a
    specific catalog (else DEFAULT_DATABASE / the login's default).
    """
    if timeout is None:
        timeout = settings.MSSQL_QUERY_TIMEOUT
    return await execute_query(
        sql,
        timeout=timeout,
        max_rows=min(10000, settings.MAX_ROWS_PER_QUERY),
        database=database,
    )


async def get_database_info() -> dict:
    """
    Fetch general database information.
    """
    try:
        sql = """
        SELECT
            DB_NAME() as database_name,
            @@VERSION as version,
            SERVERPROPERTY('MachineName') as machine_name,
            SERVERPROPERTY('InstanceName') as instance_name
        """
        result = await execute_schema_query(sql)
        if result.rows:
            return dict(zip(result.columns, result.rows[0], strict=False))
        return {}
    except Exception as e:
        logger.exception("Error fetching database info: %s", e)
        return {"error": str(e)}


async def check_connection() -> bool:
    """
    Test database connectivity.
    """
    try:
        await execute_query("SELECT 1 as test", timeout=5)
        return True
    except Exception as e:
        logger.error("Connection check failed: %s", e)
        return False
