"""The alert catalog: every alert users can enable, disable and tune.

State alerts hold a severity that later clears (log 92% full). Event alerts
are one-off occurrences that never clear (a deadlock, a failed job) and are
delivered once each. Default thresholds mirror the `alerts:` section of
.claude/knowledge-base/_static/thresholds.yaml; a test keeps them in sync.
"""

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple

Kind = Literal["state", "event"]
Tier = Literal["fast", "standard", "slow", "daily"]
Direction = Literal["above", "below"]

# Seconds between evaluations. "fast" runs every collector cycle.
TIER_SECONDS: Dict[str, int] = {"fast": 60, "standard": 300, "slow": 3600, "daily": 86400}

# Alerts about Data Eyes itself are recorded under this pseudo-instance.
SELF_INSTANCE = "Data Eyes"

VIEW_SERVER_STATE = "VIEW SERVER STATE"
MSDB_READ = "SELECT on msdb tables"
ERROR_LOG = "securityadmin (xp_readerrorlog) — high privilege"
DEFINITIONS = "VIEW ANY DEFINITION"
OLA_COMMAND_LOG = "SELECT on master.dbo.CommandLog (Ola Hallengren)"


@dataclass(frozen=True)
class AlertDefinition:
    key: str
    name: str
    group: str
    kind: Kind
    tier: Tier
    description: str
    unit: Optional[str] = None
    direction: Direction = "above"
    warning: Optional[float] = None
    critical: Optional[float] = None
    default_enabled: bool = True
    confirm_samples: int = 1
    permission: str = VIEW_SERVER_STATE
    per_database: bool = False
    scope: Literal["instance", "data_eyes"] = "instance"

    @property
    def has_thresholds(self) -> bool:
        return self.warning is not None or self.critical is not None


def _a(key, name, group, kind, tier, description, **kwargs) -> AlertDefinition:
    return AlertDefinition(key=key, name=name, group=group, kind=kind, tier=tier, description=description, **kwargs)


CATALOG: Tuple[AlertDefinition, ...] = (
    # Availability
    _a("sql_server_connection", "SQL Server Connection", "Availability", "state", "fast",
       "The instance cannot be reached. Other checks pause until it is back.",
       confirm_samples=2, permission="CONNECT SQL"),
    _a("sql_server_restarted", "SQL Server Restarted", "Availability", "event", "fast",
       "The SQL Server service start time changed since the last check."),
    _a("agent_service_stopped", "SQL Agent Stopped", "Availability", "state", "standard",
       "SQL Server Agent is not running, so scheduled jobs (backups, CHECKDB) silently stop."),
    _a("database_status", "Database Status", "Availability", "state", "fast",
       "A database is SUSPECT, RECOVERY_PENDING or EMERGENCY (critical), or OFFLINE/RESTORING (warning).",
       per_database=True, permission="public"),
    _a("ag_health", "AlwaysOn AG Health", "Availability", "state", "fast",
       "Availability group replica health, synchronization state and send/redo queue size.",
       unit="KB", warning=51200, critical=512000, per_database=True),
    _a("ag_failover", "AG Failover", "Availability", "event", "fast",
       "The primary replica of an availability group changed."),
    _a("ag_data_loss_risk", "AG Data Loss Risk", "Availability", "state", "fast",
       "Seconds of committed work on the primary that a secondary has not hardened yet (potential data loss).",
       unit="seconds", warning=60, critical=300, per_database=True),
    _a("failover_cluster_status", "Failover Cluster Status", "Availability", "state", "standard",
       "A failover cluster node or AG cluster member is down, paused or unknown."),
    _a("log_shipping_latency", "Log Shipping Latency", "Availability", "state", "standard",
       "Minutes since the last log shipping backup (primary) or restore (secondary).",
       unit="minutes", warning=60, critical=240, per_database=True, permission=MSDB_READ),

    # Backup & integrity
    _a("full_backup_age", "DB Without Full Backup", "Backup & integrity", "state", "slow",
       "Hours since the last full backup. New databases are measured from their creation time.",
       unit="hours", warning=24, critical=48, per_database=True, permission=MSDB_READ),
    _a("log_backup_age", "DB Without Log Backup", "Backup & integrity", "state", "standard",
       "Minutes since the last log backup for FULL/BULK_LOGGED databases that have a full backup.",
       unit="minutes", warning=60, critical=240, per_database=True, permission=MSDB_READ),
    _a("backup_failed", "Backup Failed", "Backup & integrity", "event", "standard",
       "The error log recorded BACKUP failed to complete (error 3041).",
       per_database=True, permission=ERROR_LOG),
    _a("checkdb_age", "CheckDB Databases", "Backup & integrity", "state", "daily",
       "Days since the last clean DBCC CHECKDB (LastGoodCheckDbTime).",
       unit="days", warning=7, critical=14, per_database=True, permission="public"),
    _a("database_corruption", "Database Corruption", "Backup & integrity", "state", "slow",
       "The latest DBCC CHECKDB run logged by Ola Hallengren's CommandLog reported an error.",
       per_database=True, permission=OLA_COMMAND_LOG),
    _a("page_corruption", "Page Corruption", "Backup & integrity", "state", "standard",
       "Unrepaired suspect pages (823/824/checksum/torn page) recorded in msdb.dbo.suspect_pages.",
       unit="pages", critical=1, per_database=True, permission=MSDB_READ),
    _a("io_corruption_errors", "I/O Errors 823/824/825", "Backup & integrity", "event", "standard",
       "The error log recorded an 823/824 I/O error or an 825 read-retry warning.",
       permission=ERROR_LOG),

    # Storage
    _a("disk_space", "Disk Space", "Storage", "state", "standard",
       "Free space on each drive that holds database files.",
       unit="GB", direction="below", warning=20, critical=5),
    _a("transaction_log_health", "Transaction Log Health", "Storage", "state", "fast",
       "Percent of the log in use, with the reason it cannot be reused and a warning when the log outgrows the data.",
       unit="%", warning=75, critical=90, per_database=True),
    _a("maxsize_growth", "MaxSize Growth", "Storage", "state", "standard",
       "A file with a capped max size is close to that cap.",
       unit="%", warning=80, critical=90, per_database=True, permission="public"),
    _a("database_growth", "Database Growth", "Storage", "state", "daily",
       "Data file growth per day, compared with the previous evaluation (ignores growth under 100 MB).",
       unit="%/day", warning=10, critical=25, per_database=True, permission="public"),
    _a("slow_file_growth", "Slow File Growth", "Storage", "event", "standard",
       "An autogrow event in the default trace took longer than the threshold.",
       unit="ms", warning=1000, critical=10000, per_database=True, permission="ALTER TRACE (default trace)"),
    _a("vlf_count", "Too Many VLFs", "Storage", "state", "daily",
       "Virtual log file count per database; high counts slow recovery and log backups.",
       unit="VLFs", warning=1000, critical=5000, per_database=True),
    _a("io_pending", "IO Pending", "Storage", "state", "fast",
       "Longest outstanding I/O request at the operating system level.",
       unit="ms", warning=5000, critical=15000, confirm_samples=2),
    _a("slow_disk", "Slow Disk", "Storage", "state", "standard",
       "Average read/write latency per database file since the previous check (files with 100+ I/Os).",
       unit="ms", warning=20, critical=50, per_database=True, confirm_samples=2),

    # Tempdb
    _a("tempdb_data_utilization", "Tempdb MDF Utilization", "Tempdb", "state", "fast",
       "Percent of allocated tempdb data file space in use.",
       unit="%", warning=85, critical=95, confirm_samples=2),
    _a("tempdb_version_store", "Tempdb Version Store", "Tempdb", "state", "standard",
       "Version store size as a percent of allocated tempdb data space.",
       unit="%", warning=30, critical=50),
    _a("tempdb_log_usage", "Tempdb Log Usage", "Tempdb", "state", "fast",
       "Percent of the tempdb transaction log in use.",
       unit="%", warning=70, critical=90),
    _a("tempdb_contention", "Tempdb Allocation Contention", "Tempdb", "state", "fast",
       "Tasks currently waiting on PAGELATCH for tempdb pages.",
       unit="tasks", warning=5, critical=20, confirm_samples=2),

    # Performance & activity
    _a("cpu_utilization", "CPU Utilization", "Performance", "state", "fast",
       "Average total CPU over the last five scheduler-monitor samples (about five minutes).",
       unit="%", warning=80, critical=95),
    _a("memory_available", "Memory Available", "Performance", "state", "fast",
       "Physical memory available to the operating system.",
       unit="MB", direction="below", warning=2048, critical=512, confirm_samples=2),
    _a("page_life_expectancy", "Page Life Expectancy", "Performance", "state", "fast",
       "Seconds a page stays in the buffer pool; a sharp drop signals memory pressure.",
       unit="seconds", direction="below", warning=300, critical=100, confirm_samples=2),
    _a("memory_grants_pending", "Memory Grants Pending", "Performance", "state", "fast",
       "Queries waiting for a memory grant before they can run.",
       unit="queries", warning=1, critical=5, confirm_samples=2),
    _a("threadpool_exhaustion", "Worker Thread Exhaustion", "Performance", "state", "fast",
       "Percent of max worker threads in use; any THREADPOOL wait is critical.",
       unit="%", warning=80, critical=95, confirm_samples=2),
    _a("blocking", "Blocked Process", "Performance", "state", "fast",
       "Longest current wait of a blocked session (merges Blocked Process and Blocked Long Process).",
       unit="seconds", warning=30, critical=120, per_database=True),
    _a("long_running_process", "Long Running Process", "Performance", "state", "fast",
       "Longest active user request, excluding backups, restores, DBCC and WAITFOR.",
       unit="seconds", warning=600, critical=3600, per_database=True),
    _a("slow_queries", "Slow Queries", "Performance", "state", "standard",
       "Highest average elapsed time among queries that ran in the last 15 minutes.",
       unit="ms", warning=5000, critical=30000, per_database=True),
    _a("deadlock", "DeadLock", "Performance", "event", "fast",
       "A deadlock captured from the system_health session by the collector.",
       per_database=True),
    _a("query_regression", "Query Plan Regression", "Performance", "state", "slow",
       "Query Store automatic tuning found queries that got slower after a plan change.",
       unit="queries", warning=1, critical=10, per_database=True, permission="VIEW DATABASE STATE"),
    _a("database_errors", "Database Errors", "Performance", "event", "standard",
       "The error log recorded an error with severity 17 or higher (20+ is critical).",
       permission=ERROR_LOG),
    _a("login_failed", "Login Failed", "Performance", "event", "standard",
       "Failed logins in the error log since the previous check.",
       unit="logins", warning=5, critical=50, permission=ERROR_LOG),

    # Maintenance
    _a("job_failed", "Job Failed", "Maintenance", "event", "standard",
       "A SQL Agent job finished with a failure.", permission=MSDB_READ),
    _a("job_disabled_or_deleted", "Job Disabled or Deleted", "Maintenance", "event", "standard",
       "A SQL Agent job was disabled or deleted since the previous check.", permission=MSDB_READ),
    _a("rebuild_failed", "Rebuild Failed", "Maintenance", "event", "standard",
       "An index rebuild/reorganize or statistics update logged an error in Ola Hallengren's CommandLog.",
       per_database=True, permission=OLA_COMMAND_LOG),
    _a("index_fragmentation", "Index Fragmentation", "Maintenance", "state", "daily",
       "Highest fragmentation among indexes over 1,000 pages. Scans every database; off by default.",
       unit="%", warning=30, critical=60, per_database=True, default_enabled=False),
    _a("stale_statistics", "Stale Statistics", "Maintenance", "state", "daily",
       "Days since statistics with 1,000+ modifications were last updated.",
       unit="days", warning=30, critical=60, per_database=True, permission=DEFINITIONS),
    _a("identity_values", "Identity Values / Int-Bigint Limit", "Maintenance", "state", "daily",
       "Percent of an identity column's data type range already used.",
       unit="%", warning=80, critical=90, per_database=True, permission=DEFINITIONS),
    _a("new_database", "New Database Not Covered", "Maintenance", "event", "standard",
       "A database was created or restored; the message says whether it has a full backup yet.",
       per_database=True, permission=MSDB_READ),
    _a("version_support", "Server Needs Hotfix", "Maintenance", "state", "daily",
       "Days until the SQL Server version leaves Microsoft extended support (negative = unsupported).",
       unit="days", direction="below", warning=365, critical=0, permission="public"),

    # Configuration & security
    _a("config_changed", "Server Configuration Changed", "Configuration & security", "event", "standard",
       "A server setting (sp_configure) changed value.", permission="public"),
    _a("max_server_memory_unset", "Max Server Memory Not Set", "Configuration & security", "state", "daily",
       "max server memory is left at the default or above physical memory."),
    _a("auto_shrink_close", "Auto-Shrink or Auto-Close On", "Configuration & security", "state", "daily",
       "A user database has AUTO_SHRINK or AUTO_CLOSE enabled.", per_database=True, permission="public"),
    _a("page_verify", "Page Verify Not CHECKSUM", "Configuration & security", "state", "daily",
       "A database uses TORN_PAGE_DETECTION or NONE instead of CHECKSUM.", per_database=True, permission="public"),
    _a("sysadmin_changed", "Sysadmin Membership Changed", "Configuration & security", "event", "standard",
       "A login was added to or removed from the sysadmin role.", permission=DEFINITIONS),
    _a("login_created", "New Login Created", "Configuration & security", "event", "standard",
       "A server login was created.", permission=DEFINITIONS),
    _a("sa_enabled", "sa Login Enabled", "Configuration & security", "state", "daily",
       "The built-in sa login (SID 0x01) is enabled.", permission=DEFINITIONS),
    _a("certificate_expiry", "Certificate Expiry", "Configuration & security", "state", "daily",
       "Days until a certificate in master (TDE, backup encryption) expires.",
       unit="days", direction="below", warning=30, critical=7, permission=DEFINITIONS),

    # Data Eyes
    _a("notification_delivery_failing", "Notification Channel Failing", "Data Eyes", "state", "standard",
       "Failed deliveries per notification channel in the last hour. Delivered through the other channels.",
       unit="failures", warning=1, critical=3, permission="none (repository)", scope="data_eyes"),
)

CATALOG_BY_KEY: Dict[str, AlertDefinition] = {definition.key: definition for definition in CATALOG}

# Prefix for alert rows in metric_snapshot, keeping them apart from the
# dashboard's fleet categories that share that table.
SNAPSHOT_PREFIX = "alert."


def title(key: str) -> str:
    definition = CATALOG_BY_KEY.get(key)
    return definition.name if definition else key
