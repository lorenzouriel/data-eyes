"""Availability: restarts, Agent, database state, AGs, clusters, log shipping."""

from app.alerts.checks.registry import TO_UTC
from app.alerts.checks.registry import check
from app.alerts.checks.registry import number
from app.alerts.checks.registry import utc
from app.alerts.models import Finding
from app.alerts.models import Occurrence


@check("sql_server_connection")
async def sql_server_connection(ctx):
    # The engine probes the connection itself before running other checks;
    # reaching this point means the probe succeeded.
    return [Finding("SQL Server", detail="Reachable")]


@check("sql_server_restarted")
async def sql_server_restarted(ctx):
    rows = await ctx.query(f"""
    SELECT CONVERT(varchar(23), sqlserver_start_time, 121) AS StartTime,
           {TO_UTC.format("sqlserver_start_time")} AS StartTimeUtc
    FROM sys.dm_os_sys_info
    """)
    if not rows:
        return []
    started, previous = rows[0]["StartTime"], ctx.memory.get("start_time")
    ctx.memory["start_time"] = started
    if previous is None or previous == started:
        return []
    return [Occurrence(f"start:{started}", utc(rows[0]["StartTimeUtc"], ctx.now), "SQL Server service",
                       detail=f"started at {started} (server time); previous start {previous}", floor="WARNING")]


@check("agent_service_stopped")
async def agent_service_stopped(ctx):
    rows = await ctx.query("""
    SELECT servicename AS ServiceName, status_desc AS StatusDesc, startup_type_desc AS StartupType
    FROM sys.dm_server_services
    WHERE servicename LIKE N'SQL Server Agent%'
    """)
    findings = []
    for row in rows:
        stopped = row["StatusDesc"] != "Running" and row["StartupType"] != "Disabled"
        findings.append(Finding(row["ServiceName"], detail=f"{row['StatusDesc']} (startup {row['StartupType']})",
                                floor="CRITICAL" if stopped else None))
    return findings


_STATE_SEVERITY = {"SUSPECT": "CRITICAL", "RECOVERY_PENDING": "CRITICAL", "EMERGENCY": "CRITICAL",
                   "OFFLINE": "WARNING", "RESTORING": "WARNING", "RECOVERING": "WARNING", "OFFLINE_SECONDARY": "WARNING"}


@check("database_status")
async def database_status(ctx):
    rows = await ctx.query("""
    SELECT d.name AS DatabaseName, d.state_desc AS StateDesc,
           CASE WHEN dm.mirroring_role = 2 THEN 1 ELSE 0 END AS IsMirror
    FROM sys.databases d
    LEFT JOIN sys.database_mirroring dm ON dm.database_id = d.database_id
    WHERE d.state_desc <> N'ONLINE'
    """)
    findings = []
    for row in rows:
        # A mirroring partner is RESTORING by design.
        floor = None if row["IsMirror"] else _STATE_SEVERITY.get(row["StateDesc"], "WARNING")
        findings.append(Finding(row["DatabaseName"], database=row["DatabaseName"], detail=row["StateDesc"], floor=floor))
    return findings


@check("ag_health")
async def ag_health(ctx):
    rows = await ctx.query("""
    SELECT ag.name AS AgName, DB_NAME(drs.database_id) AS DatabaseName, ar.replica_server_name AS Replica,
           drs.synchronization_state_desc AS SyncState, drs.synchronization_health_desc AS SyncHealth,
           drs.log_send_queue_size AS LogSendQueueKB, drs.redo_queue_size AS RedoQueueKB
    FROM sys.dm_hadr_database_replica_states drs
    JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id
    JOIN sys.availability_groups ag ON ag.group_id = drs.group_id
    """)
    findings = []
    for row in rows:
        queues = [v for v in (number(row["LogSendQueueKB"]), number(row["RedoQueueKB"])) if v is not None]
        floor = None
        if row["SyncHealth"] == "NOT_HEALTHY" or row["SyncState"] == "NOT SYNCHRONIZING":
            floor = "CRITICAL"
        elif row["SyncHealth"] == "PARTIALLY_HEALTHY":
            floor = "WARNING"
        findings.append(Finding(f"{row['AgName']}/{row['DatabaseName']} on {row['Replica']}", max(queues) if queues else None,
                                database=row["DatabaseName"], detail=f"{row['SyncState']}, {row['SyncHealth']}", floor=floor))
    return findings


@check("ag_failover")
async def ag_failover(ctx):
    rows = await ctx.query("""
    SELECT ag.name AS AgName, ags.primary_replica AS PrimaryReplica
    FROM sys.dm_hadr_availability_group_states ags
    JOIN sys.availability_groups ag ON ag.group_id = ags.group_id
    """)
    current = {row["AgName"]: row["PrimaryReplica"] for row in rows if row["PrimaryReplica"]}
    previous = ctx.memory.get("primary")
    ctx.memory["primary"] = {**(previous or {}), **current}
    if previous is None:
        return []
    stamp = ctx.now.strftime("%Y%m%d%H%M")
    return [Occurrence(f"{ag}:{replica}:{stamp}", ctx.now, ag, detail=f"primary moved from {previous[ag]} to {replica}", floor="WARNING")
            for ag, replica in current.items() if ag in previous and previous[ag] != replica]


@check("ag_data_loss_risk")
async def ag_data_loss_risk(ctx):
    rows = await ctx.query("""
    SELECT ag.name AS AgName, DB_NAME(p.database_id) AS DatabaseName, ar.replica_server_name AS Replica,
           ar.availability_mode_desc AS AvailabilityMode,
           DATEDIFF(SECOND, s.last_commit_time, p.last_commit_time) AS LagSeconds
    FROM sys.dm_hadr_database_replica_states p
    JOIN sys.dm_hadr_database_replica_states s ON s.group_database_id = p.group_database_id AND s.is_local = 0
    JOIN sys.availability_replicas ar ON ar.replica_id = s.replica_id
    JOIN sys.availability_groups ag ON ag.group_id = p.group_id
    WHERE p.is_local = 1 AND p.is_primary_replica = 1
    """)
    return [Finding(f"{row['AgName']}/{row['DatabaseName']} on {row['Replica']}",
                    max(0.0, number(row["LagSeconds"])) if row["LagSeconds"] is not None else None,
                    database=row["DatabaseName"], detail=row["AvailabilityMode"]) for row in rows]


@check("failover_cluster_status")
async def failover_cluster_status(ctx):
    rows = await ctx.query("""
    SET NOCOUNT ON;
    CREATE TABLE #n (NodeName nvarchar(256), NodeType nvarchar(60), NodeState nvarchar(60));
    INSERT INTO #n SELECT NodeName, N'FCI node', status_description FROM sys.dm_os_cluster_nodes;
    IF CAST(SERVERPROPERTY('IsHadrEnabled') AS int) = 1
        INSERT INTO #n SELECT member_name, member_type_desc, member_state_desc FROM sys.dm_hadr_cluster_members;
    SELECT NodeName, NodeType, NodeState FROM #n;
    """)
    findings = []
    for row in rows:
        state = (row["NodeState"] or "unknown").upper()
        floor = None if state == "UP" else "CRITICAL" if state == "DOWN" else "WARNING"
        findings.append(Finding(f"{row['NodeName']} ({row['NodeType']})", detail=state, floor=floor))
    return findings


@check("log_shipping_latency")
async def log_shipping_latency(ctx):
    rows = await ctx.query("""
    SET NOCOUNT ON;
    CREATE TABLE #ls (RoleName nvarchar(20), DatabaseName sysname, Minutes int NULL);
    IF OBJECT_ID(N'msdb.dbo.log_shipping_monitor_primary') IS NOT NULL
    BEGIN
        INSERT INTO #ls SELECT N'backup', primary_database, DATEDIFF(MINUTE, last_backup_date, GETDATE())
        FROM msdb.dbo.log_shipping_monitor_primary;
        INSERT INTO #ls SELECT N'restore', secondary_database, DATEDIFF(MINUTE, last_restored_date, GETDATE())
        FROM msdb.dbo.log_shipping_monitor_secondary;
    END;
    SELECT RoleName, DatabaseName, Minutes FROM #ls;
    """)
    return [Finding(f"{row['DatabaseName']} ({row['RoleName']})", number(row["Minutes"]), database=row["DatabaseName"],
                    detail="" if row["Minutes"] is not None else f"no {row['RoleName']} recorded",
                    floor=None if row["Minutes"] is not None else "WARNING") for row in rows]
