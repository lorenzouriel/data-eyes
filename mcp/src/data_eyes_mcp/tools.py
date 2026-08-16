"""
MCP Tools for Data Eyes MCP Server.

Implements @mcp.tool() decorated functions that are exposed to MCP clients.
Each tool validates input, applies policies, executes DB queries, and returns results.
"""

import base64
import logging
import time
from typing import Optional, Any

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings

from .config import settings

from .db import execute_query, execute_schema_query, get_database_info as fetch_database_info, check_connection, DatabaseError, request_credentials
from .policy import validate_with_audit, QueryMode, get_query_mode, explain_policy
from .metrics import MetricsContext, record_query_blocked
from .utils import format_table, format_json, result_summary

logger = logging.getLogger(__name__)


# HTTP headers a remote client may send (e.g. in its MCP config) to authenticate
# as its own SQL login for the duration of a request, overriding the server's
# default credentials. Passwords travel in headers, so use HTTPS / a trusted
# network in production.
#
# HTTP header values must be Latin-1 (bytes 0-255), so a value with non-ASCII
# characters (e.g. accented passwords) cannot be sent raw — many clients refuse
# to. For those, send the base64 of the UTF-8 value in the "<header>-B64" variant
# instead; it takes precedence over the plain header.
_HDR_USER = "X-MSSQL-User"
_HDR_PASSWORD = "X-MSSQL-Password"
_HDR_TRUSTED = "X-MSSQL-Trusted-Connection"
_B64_SUFFIX = "-B64"


def _header_value(headers, name: str) -> Optional[str]:
    """Return a header's value, preferring its base64 variant (<name>-B64).

    The base64 form lets clients pass values containing non-Latin-1 characters,
    which raw HTTP headers cannot carry.
    """
    b64 = headers.get(name + _B64_SUFFIX)
    if b64:
        try:
            return base64.b64decode(b64).decode("utf-8")
        except Exception:
            logger.warning("Ignoring malformed base64 header: %s", name + _B64_SUFFIX)
            return None
    return headers.get(name)


def _creds_from_ctx(ctx: Optional[Context]) -> dict:
    """Extract optional per-request SQL credentials from the MCP request headers.

    Returns a dict suitable for request_credentials(**...); empty when none are
    provided (e.g. stdio transport, or a client that sends no credential headers).
    """
    if ctx is None:
        return {}
    try:
        request = ctx.request_context.request
    except Exception:
        return {}
    headers = getattr(request, "headers", None)
    if not headers:
        return {}

    creds: dict = {}
    user = _header_value(headers, _HDR_USER)
    password = _header_value(headers, _HDR_PASSWORD)
    trusted_raw = _header_value(headers, _HDR_TRUSTED)
    if user:
        creds["user"] = user
    if password:
        creds["password"] = password
    if trusted_raw is not None:
        creds["trusted"] = trusted_raw.strip().lower() in ("1", "true", "yes", "on")
    return creds

def _get_transport_security():
    """Configure transport security based on ALLOWED_HOST setting."""
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"]
    
    if settings.ALLOWED_HOST:
        allowed_hosts.append(f"{settings.ALLOWED_HOST}:*")
        allowed_origins.append(f"http://{settings.ALLOWED_HOST}:*")
    
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

# Guidance sent to MCP clients on initialize, so agents use the tools effectively.
_INSTRUCTIONS = """\
This server exposes a Microsoft SQL Server database.

To find what you need efficiently:
- Discover databases with `list_databases`, then explore any of them: the
  discovery tools (`list_schemas`, `list_tables`, `describe_table`,
  `schema_discovery`, `get_relationships`) all take a `database` argument to look
  inside a specific database, not just the current one.
- `describe_table` gives a table's columns, types, keys and descriptions;
  `get_relationships` gives foreign keys (for JOINs); `sample_table` shows example
  rows; `distinct_values` shows a column's typical values before you filter on it.
- Run queries with `execute_sql`: format="json" gives a valid JSON envelope for
  reliable field parsing; for large results prefer "table"/"csv" (more compact)
  and control size with `max_rows`. Raise `timeout` for slow queries; pass
  `database` to run in a specific database.

Conventions:
- The default database follows the connected login (override per call with the
  `database` argument, or server-wide with DEFAULT_DATABASE).
- Cross-database queries work in a SINGLE statement via fully-qualified names —
  DATABASE.schema.table — including JOINs across databases. You do NOT need
  multiple statements or USE; multi-statement input is rejected.
- Non-ASCII text (e.g. accented characters) is handled correctly; use N'...' for
  NVARCHAR string literals.
- Only single statements are allowed; write operations require the server to be
  write-enabled and a login with the right permissions.
"""

# Create MCP server instance with transport security
mcp = FastMCP(
    "data-eyes-mcp",
    instructions=_INSTRUCTIONS,
    transport_security=_get_transport_security(),
)


@mcp.tool()
async def execute_sql(
    sql: str,
    format: str = "table",
    timeout: Optional[int] = None,
    max_rows: Optional[int] = None,
    database: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Execute a SQL statement against the SQL Server database.

    SELECT queries run in read-only mode by default. Write operations
    (INSERT/UPDATE/DELETE) only succeed if the server is started with
    ENABLE_WRITES=true and a matching ADMIN_CONFIRM token; otherwise they are
    rejected by the policy engine. For writes, the affected-row count is returned.

    Args:
        sql: SQL statement to execute.
        format: Output format for result sets - 'table', 'json', or 'csv'
            (default: 'table'). Use 'json' when you need to parse specific fields
            reliably (it returns a valid JSON envelope with row_count/truncated).
            For large result sets 'csv' or 'table' are far more compact than json
            (json repeats every column name on every row); the real lever for big
            data is `max_rows`, not the format.
        timeout: Per-query timeout in seconds. Overrides the server default
            (MSSQL_QUERY_TIMEOUT) for this call only — raise it for slow,
            complex queries such as large JOINs or CROSS APPLY.
        max_rows: Maximum rows to return for this call. Overrides the server
            default (MAX_ROWS_PER_QUERY). The output flags when results are
            truncated.
        database: Run in this database (initial catalog) so unqualified names
            resolve there. Cross-database queries also work without it via
            fully-qualified names, e.g. [OtherDb].schema.table, including JOINs.

    Returns:
        For 'json': a JSON object {columns, row_count, truncated, rows}. For
        'table'/'csv': the rendered rows followed by a summary line. For write
        statements: a confirmation with the affected-row count.
    """
    client_id = "unknown"  # Could be extracted from request context in production
    tool_name = "execute_sql"

    start_time = time.time()

    # Validate policy
    is_allowed, reason = validate_with_audit(sql, client_id=client_id, tool_name=tool_name)
    if not is_allowed:
        record_query_blocked(reason or "unknown")
        return f"ERROR: Query not allowed - {reason}"

    # Execute query with metrics tracking
    with MetricsContext(tool_name) as metrics:
        try:
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_query(sql, timeout=timeout, max_rows=max_rows, database=database)
            metrics.set_rows(len(res.rows))

            # Write statement / no result set: report affected rows.
            if not res.columns:
                if res.rowcount >= 0:
                    return f"OK: {res.rowcount} row(s) affected."
                return "OK: statement executed (no result set)."

            # JSON mode returns a single valid JSON document (envelope) with the
            # metadata inside it — no trailing summary line, so it parses cleanly.
            if format.lower() == "json":
                import json as _json
                from .utils import rows_to_dicts
                envelope = {
                    "columns": res.columns,
                    "row_count": len(res.rows),
                    "truncated": res.truncated,
                    "rows": rows_to_dicts(res.columns, res.rows),
                }
                return _json.dumps(envelope, indent=2, default=str)

            # Human-readable formats: render, then append a summary line that
            # flags truncation explicitly so it is never silent.
            if format.lower() == "csv":
                from .utils import format_csv
                result = format_csv(res.columns, res.rows)
            else:  # table (default)
                result = format_table(res.columns, res.rows)

            summary = result_summary(res.columns, res.rows)
            if res.truncated:
                summary += " — TRUNCATED (more rows available; raise max_rows to see them)"
            return f"{result}\n\n[{summary}]"

        except Exception as e:
            logger.exception("Query execution failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def list_schemas(database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    List all schemas in the current database.

    Returns:
        Formatted list of schema names
    """
    tool_name = "list_schemas"

    with MetricsContext(tool_name) as metrics:
        try:
            sql = """
            SELECT
                schema_id,
                name,
                principal_id
            FROM sys.schemas
            ORDER BY name
            """
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql, database=database)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return "No schemas found."

            # Format simple list
            schema_names = [row[1] for row in res.rows]
            return "\n".join(f"  - {name}" for name in schema_names)

        except Exception as e:
            logger.exception("list_schemas failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def list_tables(schema: Optional[str] = None, limit: int = 200, database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    List tables in the database, optionally filtered by schema.

    Args:
        schema: Optional schema name to filter (default: all schemas)
        limit: Maximum number of tables to return (default: 200)

    Returns:
        Formatted list of tables
    """
    tool_name = "list_tables"

    if limit < 1:
        return "ERROR: limit must be >= 1"
    if limit > 1000:
        limit = 1000  # Cap at 1000

    with MetricsContext(tool_name) as metrics:
        try:
            if schema:
                # Validate schema name to prevent injection
                from .utils import escape_sql_string
                schema_filter = f"AND s.name = {escape_sql_string(schema)}"
            else:
                schema_filter = ""

            sql = f"""
            SELECT TOP {limit}
                s.name as schema_name,
                t.name as table_name,
                t.object_id
            FROM sys.tables t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE t.type = 'U'  -- User tables only
            {schema_filter}
            ORDER BY s.name, t.name
            """

            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql, database=database)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return "No tables found."

            # Format results
            result = format_table(res.columns, res.rows)
            return f"{result}\n\n[{len(res.rows)} table(s)]"

        except Exception as e:
            logger.exception("list_tables failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def schema_discovery(schema: Optional[str] = None, database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Discover schema information: tables, columns, types, and constraints.

    Returns detailed metadata about database objects as JSON.

    Args:
        schema: Optional schema name to filter (default: all schemas)

    Returns:
        JSON-formatted schema metadata
    """
    tool_name = "schema_discovery"

    with MetricsContext(tool_name) as metrics:
        try:
            if schema:
                from .utils import escape_sql_string
                schema_filter = f"WHERE s.name = {escape_sql_string(schema)}"
            else:
                schema_filter = ""

            sql = f"""
            SELECT
                s.name as schema_name,
                t.name as table_name,
                c.name as column_name,
                ty.name as column_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                CASE WHEN c.column_id IS NOT NULL THEN 1 ELSE 0 END as has_default,
				ep.value as table_description
            FROM sys.schemas s
            INNER JOIN sys.tables t ON s.schema_id = t.schema_id
            INNER JOIN sys.columns c ON t.object_id = c.object_id
            INNER JOIN sys.types ty ON c.user_type_id = ty.user_type_id
			LEFT JOIN sys.extended_properties ep ON ep.major_id = c.object_id AND ep.minor_id = c.column_id
            {schema_filter}
            ORDER BY schema_name, table_name, column_name
            """

            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql, timeout=60, database=database)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return "No schema information found."

            # Convert to JSON structure
            from .utils import format_json
            result = format_json(res.columns, res.rows)
            return result

        except Exception as e:
            logger.exception("schema_discovery failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def describe_table(table: str, database: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Describe a single table's structure: columns, data types, length,
    nullability, primary-key membership, and column descriptions.

    A focused alternative to schema_discovery when you only need one table.

    Args:
        table: Table name, optionally schema-qualified (e.g. 'dbo.users' or
            'users'). Without a schema prefix, all schemas are matched.

    Returns:
        JSON-formatted column metadata, or a not-found message.
    """
    tool_name = "describe_table"
    from .utils import escape_sql_string, format_json

    # Split optional schema qualifier ('schema.table').
    if "." in table:
        schema_name, table_name = table.split(".", 1)
    else:
        schema_name, table_name = None, table

    with MetricsContext(tool_name) as metrics:
        try:
            filters = [f"t.name = {escape_sql_string(table_name)}"]
            if schema_name:
                filters.append(f"s.name = {escape_sql_string(schema_name)}")
            where = " AND ".join(filters)

            sql = f"""
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.column_id,
                c.name AS column_name,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key,
                CAST(cep.value AS NVARCHAR(MAX)) AS column_description,
                CAST(tep.value AS NVARCHAR(MAX)) AS table_description
            FROM sys.tables t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns c ON t.object_id = c.object_id
            INNER JOIN sys.types ty ON c.user_type_id = ty.user_type_id
            LEFT JOIN (
                SELECT ic.object_id, ic.column_id
                FROM sys.index_columns ic
                INNER JOIN sys.indexes i
                    ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                WHERE i.is_primary_key = 1
            ) pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
            LEFT JOIN sys.extended_properties cep
                ON cep.major_id = c.object_id AND cep.minor_id = c.column_id
                AND cep.name = 'MS_Description'
            LEFT JOIN sys.extended_properties tep
                ON tep.major_id = t.object_id AND tep.minor_id = 0
                AND tep.name = 'MS_Description'
            WHERE {where}
            ORDER BY s.name, t.name, c.column_id
            """
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql, database=database)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return f"Table not found: {table}"

            return format_json(res.columns, res.rows)

        except Exception as e:
            logger.exception("describe_table failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def get_database_info(ctx: Optional[Context] = None) -> str:
    """
    Get general information about the database and server.

    Returns:
        JSON-formatted database information
    """
    tool_name = "get_database_info"

    with MetricsContext(tool_name) as metrics:
        try:
            with request_credentials(**_creds_from_ctx(ctx)):
                info = await fetch_database_info()
            metrics.set_rows(1)

            from .utils import format_json
            # Convert dict to JSON-like format
            result = format_json(
                list(info.keys()),
                [tuple(info.values())]
            )
            return result

        except Exception as e:
            logger.exception("get_database_info failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def get_policy_info() -> str:
    """
    Get current policy and safety settings.

    Returns:
        JSON-formatted policy information
    """
    tool_name = "get_policy_info"

    with MetricsContext(tool_name) as metrics:
        try:
            policy = explain_policy()
            metrics.set_rows(1)

            import json
            return json.dumps(policy, indent=2)

        except Exception as e:
            logger.exception("get_policy_info failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def check_db_connection(ctx: Optional[Context] = None) -> str:
    """
    Check if the database connection is active and healthy.

    Returns:
        Connection status message
    """
    tool_name = "check_db_connection"

    with MetricsContext(tool_name) as metrics:
        try:
            with request_credentials(**_creds_from_ctx(ctx)):
                is_connected = await check_connection()
            metrics.set_rows(1)

            if is_connected:
                return "✓ Database connection is healthy"
            else:
                return "✗ Database connection failed"

        except Exception as e:
            logger.exception("check_db_connection failed")
            return f"ERROR: Database connection check failed - {str(e)}"


@mcp.tool()
async def get_relationships(
    table: Optional[str] = None,
    schema: Optional[str] = None,
    database: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    List foreign-key relationships (parent table.column -> referenced table.column).

    Use this to learn how tables join before writing JOINs. Optionally filter to a
    single table (matches the FK's parent or referenced side) and/or a schema.

    Returns:
        JSON list of relationships, or a message if none are found.
    """
    tool_name = "get_relationships"
    from .utils import escape_sql_string, format_json

    with MetricsContext(tool_name) as metrics:
        try:
            filters = []
            if table:
                t = escape_sql_string(table)
                filters.append(f"(pt.name = {t} OR rt.name = {t})")
            if schema:
                s = escape_sql_string(schema)
                filters.append(f"(ps.name = {s} OR rs.name = {s})")
            where = ("WHERE " + " AND ".join(filters)) if filters else ""

            sql = f"""
            SELECT
                fk.name AS fk_name,
                ps.name AS parent_schema,
                pt.name AS parent_table,
                pc.name AS parent_column,
                rs.name AS referenced_schema,
                rt.name AS referenced_table,
                rc.name AS referenced_column
            FROM sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.tables pt ON pt.object_id = fk.parent_object_id
            INNER JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
            INNER JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
            INNER JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
            INNER JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
            INNER JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
            {where}
            ORDER BY ps.name, pt.name, fk.name, fkc.constraint_column_id
            """
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql, database=database)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return "No foreign-key relationships found."
            return format_json(res.columns, res.rows)

        except Exception as e:
            logger.exception("get_relationships failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


def _qualified_name(table: str) -> Optional[str]:
    """Turn 'db.schema.table' / 'schema.table' / 'table' into a safely bracketed name."""
    from .utils import escape_sql_identifier
    parts = [p.strip() for p in table.split(".")]
    if not table.strip() or len(parts) > 3 or any(not p for p in parts):
        return None
    return ".".join(escape_sql_identifier(p) for p in parts)


@mcp.tool()
async def sample_table(table: str, limit: int = 5, ctx: Optional[Context] = None) -> str:
    """
    Return a few example rows from a table, to understand its data shape and values.

    Args:
        table: Table name, optionally schema-/database-qualified
            (e.g. 'dbo.users' or 'MyDb.dbo.users').
        limit: Number of rows to return (default 5, max 100).

    Returns:
        JSON rows, or a message if the table is empty.
    """
    tool_name = "sample_table"
    from .utils import format_json

    if limit < 1:
        return "ERROR: limit must be >= 1"
    limit = min(limit, 100)
    qualified = _qualified_name(table)
    if not qualified:
        return "ERROR: invalid table name"

    with MetricsContext(tool_name) as metrics:
        try:
            sql = f"SELECT TOP {limit} * FROM {qualified}"
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_query(sql, max_rows=limit)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return f"No rows in {table}."
            return format_json(res.columns, res.rows)

        except Exception as e:
            logger.exception("sample_table failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def distinct_values(table: str, column: str, limit: int = 20, ctx: Optional[Context] = None) -> str:
    """
    Show a column's most frequent distinct values with counts, to learn what to
    filter on (e.g. the set of status codes or categories in a column).

    Args:
        table: Table name, optionally schema-/database-qualified.
        column: Column name.
        limit: Max distinct values to return (default 20, max 200).

    Returns:
        JSON list of {value, count}, most frequent first.
    """
    tool_name = "distinct_values"
    from .utils import escape_sql_identifier, format_json

    if limit < 1:
        return "ERROR: limit must be >= 1"
    limit = min(limit, 200)
    qualified = _qualified_name(table)
    if not qualified:
        return "ERROR: invalid table name"
    if not column.strip():
        return "ERROR: column is required"
    col = escape_sql_identifier(column.strip())

    with MetricsContext(tool_name) as metrics:
        try:
            sql = (
                f"SELECT TOP {limit} {col} AS value, COUNT(*) AS count "
                f"FROM {qualified} GROUP BY {col} ORDER BY COUNT(*) DESC"
            )
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_query(sql, max_rows=limit)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return f"No values found for {column} in {table}."
            return format_json(res.columns, res.rows)

        except Exception as e:
            logger.exception("distinct_values failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def list_databases(ctx: Optional[Context] = None) -> str:
    """
    List the databases the connected login can access.

    Use this to discover which databases exist for cross-database work. Any of
    them can be targeted via the `database` argument of the discovery tools, or
    queried directly with fully-qualified names (e.g. [OtherDb].schema.table).

    Returns:
        JSON list of {name, database_id, state} for accessible databases.
    """
    tool_name = "list_databases"
    from .utils import format_json

    with MetricsContext(tool_name) as metrics:
        try:
            sql = (
                "SELECT name, database_id, state_desc AS state "
                "FROM sys.databases WHERE HAS_DBACCESS(name) = 1 ORDER BY name"
            )
            with request_credentials(**_creds_from_ctx(ctx)):
                res = await execute_schema_query(sql)
            metrics.set_rows(len(res.rows))

            if not res.rows:
                return "No accessible databases found."
            return format_json(res.columns, res.rows)

        except Exception as e:
            logger.exception("list_databases failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"
