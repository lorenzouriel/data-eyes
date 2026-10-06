"""Check registry and helpers shared by the check modules.

Every check is read-only. SQL returns raw measurements; severity comes from
the user-editable thresholds in app/modules/alerts/evaluation.py. Details
carry metadata only (names, files, logins) and never query text, because
they are sent to chat, email and SMS.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional

from app.modules.alerts.models import CheckContext

Check = Callable[[CheckContext], Awaitable[list]]
CHECKS: Dict[str, Check] = {}

# DATEADD expression converting a server-local datetime column to UTC.
TO_UTC = "DATEADD(MINUTE, DATEDIFF(MINUTE, GETDATE(), GETUTCDATE()), {})"
_SERVER_TIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")


def check(key: str):
    def register(function: Check) -> Check:
        CHECKS[key] = function
        return function
    return register


def utc(value, default: datetime) -> datetime:
    """Parse a DMV timestamp (already converted to UTC in SQL) as aware UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return default
    else:
        return default
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def number(value) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def digest(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]


def server_time(value: str) -> str:
    """Validate a watermark before it is placed in SQL text."""
    if not isinstance(value, str) or not _SERVER_TIME.match(value):
        raise ValueError("Invalid server time watermark")
    return value


def as_datetime(value: str) -> str:
    """SQL literal for a validated watermark. Style 121 is explicit because a
    bare 'yyyy-mm-dd hh:mi:ss' string converts to datetime according to the
    session language and would read as year-day-month under DMY."""
    return f"CONVERT(datetime, '{server_time(value)}', 121)"


async def server_now(ctx: CheckContext) -> str:
    rows = await ctx.query("SELECT CONVERT(varchar(23), GETDATE(), 121) AS ServerNow")
    return rows[0]["ServerNow"]


async def read_error_log(ctx: CheckContext, search: str, limit: int = 500) -> Optional[List[dict]]:
    """New error log lines matching a fixed search string since the last
    check. Returns None on the first run, which only records a baseline so a
    newly enabled alert does not replay the whole log. Lines at the boundary
    timestamp are remembered and skipped on the next read."""
    since = ctx.memory.get("since")
    if since is None:
        ctx.memory.update(since=await server_now(ctx), seen=[])
        return None
    sql = f"""
    SET NOCOUNT ON;
    DECLARE @since datetime = {as_datetime(since)};
    CREATE TABLE #log (LogDate datetime, ProcessInfo nvarchar(100), [Text] nvarchar(max));
    INSERT INTO #log EXEC master.dbo.xp_readerrorlog 0, 1, N'{search.replace("'", "''")}', NULL, @since, NULL, N'asc';
    SELECT TOP {int(limit)}
        CONVERT(varchar(23), LogDate, 121) AS LogDate,
        {TO_UTC.format("LogDate")} AS LogDateUtc,
        ProcessInfo,
        LEFT([Text], 2000) AS [Text]
    FROM #log
    ORDER BY LogDate;
    """
    rows = await ctx.query(sql)
    seen = set(ctx.memory.get("seen") or [])
    fresh = [row for row in rows if not (row["LogDate"] == since and digest(row["ProcessInfo"], row["Text"]) in seen)]
    if rows:
        newest = max(row["LogDate"] for row in rows)
        boundary = [digest(row["ProcessInfo"], row["Text"]) for row in rows if row["LogDate"] == newest]
        if newest == since:
            boundary = sorted(seen.union(boundary))
        ctx.memory.update(since=newest, seen=boundary[-200:])
    return fresh


def for_each_database(select: str, columns: str, where: str = "database_id > 4") -> str:
    """Run a per-database SELECT (run after USE <db>) across accessible online
    databases into #r(columns), then return #r. A database that errors is
    skipped rather than failing the whole check."""
    escaped = select.replace("'", "''")
    return f"""
    SET NOCOUNT ON;
    CREATE TABLE #r ({columns});
    DECLARE @db sysname, @sql nvarchar(max);
    DECLARE dbs CURSOR LOCAL FAST_FORWARD FOR
        SELECT name FROM sys.databases
        WHERE {where} AND state_desc = N'ONLINE' AND HAS_DBACCESS(name) = 1;
    OPEN dbs;
    FETCH NEXT FROM dbs INTO @db;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @sql = N'USE ' + QUOTENAME(@db) + N'; {escaped}';
        BEGIN TRY
            INSERT INTO #r EXEC sys.sp_executesql @sql;
        END TRY
        BEGIN CATCH
        END CATCH;
        FETCH NEXT FROM dbs INTO @db;
    END;
    CLOSE dbs;
    DEALLOCATE dbs;
    SELECT * FROM #r;
    """
