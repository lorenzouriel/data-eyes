"""Health implementation."""

from typing import Optional
from mcp.server.fastmcp import Context
from data_eyes_mcp.observability.metrics import MetricsContext
from data_eyes_mcp.tools.registry import mcp
from data_eyes_mcp.core.formatting import format_json
from data_eyes_mcp.tools.diagnostics.common import _filter_by_database
from data_eyes_mcp.tools.diagnostics.common import _run
from data_eyes_mcp.tools.diagnostics.queries import _sql_ag_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_backup_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_checkdb_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_db_space
from data_eyes_mcp.tools.diagnostics.queries import _sql_job_health
import logging
logger = logging.getLogger(__name__)


@mcp.tool()
async def db_space(database: Optional[str] = None, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Per-file size/free-space plus underlying drive free space — the
    "Storage" DPA-style category. A database can have plenty of free space
    inside its own files while the disk hosting it is nearly full; severity
    is driven by drive free space, the actual outage risk. Mirrors
    .claude/resources/maintenance/diagnostics/db_space_check.sql, which closed a gap where
    this logic previously only existed as inline Grafana panel SQL.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, FileName, FileType, FileSizeMB,
        FreeSpaceMB, FreeSpacePct, DriveSizeGB, DriveFreeSpaceGB, severity.
    """
    with MetricsContext("db_space") as metrics:
        try:
            sql = _filter_by_database(_sql_db_space(), database)
            res = await _run(sql, None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("db_space failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def backup_health(database: Optional[str] = None, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Backup health per user database: last FULL/DIFF/LOG backup and staleness.

    Reads msdb.dbo.backupset (any backup method, not just this toolkit's jobs).
    Mirrors .claude/resources/maintenance/diagnostics/backup_health_check.sql.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, RecoveryModel, LastFullBackup,
        FullBackupAgeHours, LastDiffBackup, LastLogBackup,
        LogBackupAgeMinutes (NULL for SIMPLE recovery model), severity.
    """
    with MetricsContext("backup_health") as metrics:
        try:
            sql = _filter_by_database(_sql_backup_health(), database)
            res = await _run(sql, None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("backup_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def checkdb_health(database: Optional[str] = None, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    CHECKDB staleness + active suspect pages per user database.

    Reads master.dbo.CommandLog, which only exists once Ola Hallengren's
    maintenance scripts are installed (see .claude/resources/maintenance/README.md) — a database
    never checked via that path reports LastCheckDBEndTime = NULL and
    severity = CRITICAL. Mirrors .claude/resources/maintenance/diagnostics/checkdb_staleness.sql.

    Args:
        database: Restrict to a single database (defaults to all user databases).

    Returns:
        JSON rows: DatabaseName, LastCheckDBEndTime, DaysSinceLastCheckDB,
        SuspectPageCount, severity.
    """
    with MetricsContext("checkdb_health") as metrics:
        try:
            sql = _filter_by_database(_sql_checkdb_health(), database)
            res = await _run(sql, None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No user databases found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("checkdb_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def ag_health(instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Per-database Availability Group sync health — a replica can report HEALTHY
    while one of its databases is NOT SYNCHRONIZING. Returns an empty result
    (not an error) on standalone/non-AG instances. Mirrors
    .claude/resources/maintenance/diagnostics/ag_sync_health.sql.

    Returns:
        JSON rows: DatabaseName, Replica, SyncState, SyncHealth,
        IsPrimaryReplica, LogSendQueueKB, RedoQueueKB, severity. Or a message
        if this instance has no Availability Group configured.
    """
    with MetricsContext("ag_health") as metrics:
        try:
            res = await _run(_sql_ag_health(), None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No Availability Group configured on this instance (standalone)."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("ag_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def job_health(instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Most recent run outcome and 7-day failure count per enabled SQL Agent job.

    Jobs are instance-level, not per-database — this tool has no `database`
    parameter. Mirrors .claude/resources/maintenance/diagnostics/job_failure_scan.sql.

    Returns:
        JSON rows: JobName, LastRunDateTime, LastRunStatus, LastRunMessage,
        FailuresLast7Days, severity.
    """
    with MetricsContext("job_health") as metrics:
        try:
            res = await _run(_sql_job_health(), None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No enabled SQL Agent jobs with run history found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("job_health failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"
