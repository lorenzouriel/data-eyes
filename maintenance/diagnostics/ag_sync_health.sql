-- #######################
-- AVAILABILITY GROUP SYNC HEALTH — live observation, read-only, instance-wide
-- Purpose: Per-database AG sync health (a replica can report HEALTHY while one
--          of its databases is NOT SYNCHRONIZING) — ports the query from
--          monitor/docs/availability_groups.md into a severity-classified,
--          MCP-tool-consumable form.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> availability_groups
-- Note: returns an empty result set (not an error) on standalone/non-AG
--       instances — the dashboard's AG tab should hide itself in that case.
-- #######################

;WITH Base AS (
    SELECT
        DB_NAME(drs.database_id) AS DatabaseName,
        ar.replica_server_name AS Replica,
        drs.synchronization_state_desc AS SyncState,
        drs.synchronization_health_desc AS SyncHealth,
        drs.is_primary_replica AS IsPrimaryReplica,
        drs.log_send_queue_size AS LogSendQueueKB,
        drs.redo_queue_size AS RedoQueueKB,
        CASE
            WHEN drs.synchronization_health_desc = 'NOT_HEALTHY' THEN 'CRITICAL'
            WHEN drs.synchronization_state_desc = 'NOT SYNCHRONIZING' THEN 'CRITICAL'
            WHEN drs.redo_queue_size >= 512000 OR drs.log_send_queue_size >= 512000 THEN 'CRITICAL'
            WHEN drs.synchronization_health_desc = 'PARTIALLY_HEALTHY' THEN 'WARNING'
            WHEN drs.redo_queue_size >= 51200 OR drs.log_send_queue_size >= 51200 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_hadr_database_replica_states drs
    JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id
    WHERE drs.is_local = 1
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, DatabaseName
FOR JSON AUTO, INCLUDE_NULL_VALUES
