# Availability Groups & Read Replicas

Panel documentation for **Fleet Overview** (`grafana/dashboards/fleet_overview.json`) — the dashboard that shows every registered instance side by side and validates which are Availability Group (AG) members and which are read replicas.

## How the fleet is built

The dashboard does not hardcode instance names. It uses a `datasource`-type template variable (`$instance`) filtered to any datasource named `SQL Server - *` (see `grafana/datasources.yml`). Every panel is set to **repeat** across `$instance`, so adding a new instance is just:

1. Add a new datasource block to `grafana/datasources.yml` named `SQL Server - <label>`.
2. Add its connection env vars to `.env`.
3. Restart Grafana — the new instance appears automatically, no dashboard edits needed.

## Panel: Instance Health

Single query returning the instance's `@@SERVERNAME`, current AG role, uptime, and active session count:

```sql
SELECT
    CAST(SERVERPROPERTY('ServerName') AS varchar(128)) AS instance,
    ISNULL(ars.role_desc, 'STANDALONE') AS replica_role,
    DATEDIFF(MINUTE, si.sqlserver_start_time, GETDATE()) AS uptime_min,
    (SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) AS active_sessions
FROM sys.dm_os_sys_info si
LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.is_local = 1;
```

`role_desc` comes from `sys.dm_hadr_availability_replica_states` filtered to `is_local = 1` (the replica hosted by the instance being queried). If the instance has no AG configured, the `LEFT JOIN` returns no row and `ISNULL` reports `STANDALONE`.

Color coding: **PRIMARY** = green, **SECONDARY** = blue, **STANDALONE** = gray.

## Panel: AG & Replica Detail

Answers the two questions directly: *is this instance in an AG?* and *is it a read replica?*

```sql
SELECT
    CAST(SERVERPROPERTY('ServerName') AS varchar(128)) AS instance,
    CASE WHEN CAST(SERVERPROPERTY('IsHadrEnabled') AS int) = 1 THEN 'Yes' ELSE 'No' END AS hadr_enabled,
    ISNULL(ag.name, 'N/A') AS availability_group,
    ISNULL(ars.role_desc, 'STANDALONE') AS replica_role,
    ISNULL(ars.synchronization_health_desc, 'N/A') AS sync_health,
    ISNULL(ar.secondary_role_allow_connections_desc, 'N/A') AS read_replica_allowed,
    CASE
        WHEN ars.role_desc = 'SECONDARY' AND ar.secondary_role_allow_connections_desc IN ('READ_ONLY', 'ALL') THEN 'YES'
        WHEN ars.role_desc = 'SECONDARY' THEN 'NO'
        ELSE 'N/A'
    END AS is_read_replica
FROM (SELECT 1 AS dummy) d
LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.is_local = 1
LEFT JOIN sys.availability_replicas ar ON ar.replica_id = ars.replica_id
LEFT JOIN sys.availability_groups ag ON ag.group_id = ar.group_id;
```

The `(SELECT 1 AS dummy)` anchor plus `LEFT JOIN`s guarantee exactly one row per instance regardless of AG membership, so standalone instances render cleanly instead of an empty table.

- `is_read_replica = YES` — the instance is a SECONDARY and `secondary_role_allow_connections_desc` is `READ_ONLY` or `ALL`. This is the actual "read replica" in the traditional sense.
- `is_read_replica = NO` — the instance is a SECONDARY but connections are not allowed on it (`NO` role config) — it exists for HA/failover only, not for read traffic.
- `is_read_replica = N/A` — the instance is either the PRIMARY or not in an AG at all.

## Panel: Per-Database Sync State (AG members)

```sql
SELECT
    DB_NAME(drs.database_id) AS database_name,
    ar.replica_server_name AS replica,
    drs.synchronization_state_desc AS sync_state,
    drs.synchronization_health_desc AS sync_health,
    drs.is_primary_replica,
    drs.log_send_queue_size AS log_send_queue_kb,
    drs.redo_queue_size AS redo_queue_kb
FROM sys.dm_hadr_database_replica_states drs
JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id
WHERE drs.is_local = 1
ORDER BY database_name;
```

Validates AG health at the database level, not just the replica level — a replica can report `HEALTHY` while an individual database inside it is `NOT SYNCHRONIZING`. Empty results here are expected and correct for standalone instances (no HADR enabled).

**Interpretation:**

| sync_state | Meaning |
|---|---|
| `SYNCHRONIZED` | Primary and secondary are byte-for-byte in sync (synchronous commit) |
| `SYNCHRONIZING` | Catching up (normal right after seeding, or under load) |
| `NOT SYNCHRONIZING` | Replication has stopped — investigate immediately |

| sync_health | Meaning |
|---|---|
| `HEALTHY` | Within RPO/RTO expectations |
| `PARTIALLY_HEALTHY` | One or more replicas degraded |
| `NOT_HEALTHY` | Replica unreachable or failed |

Rising `log_send_queue_kb` / `redo_queue_kb` over time indicates the secondary is falling behind — worth an alert threshold if this stays non-zero for sustained periods.

## Testing against dba-lab

`dba-lab` (`../labs/dba-lab`) models exactly this topology:

| Container | Port | Role |
|---|---|---|
| `sql-dev` | 1401 | standalone (no AG) |
| `sql-staging` | 1402 | standalone (no AG) |
| `sql-prod-1` | 1403 | AG primary (`AppDB_AG` / `AppDB`) |
| `sql-prod-2` | 1404 | AG secondary, `ALLOW_CONNECTIONS = READ_ONLY` — the read replica |

`dba-lab/scripts/ag/setup-ag.ps1` provisions the AG (master key, certificate, endpoint, `CREATE AVAILABILITY GROUP`). Once that has been run against `sql-prod-1`/`sql-prod-2`, the Fleet Overview dashboard should show `sql-prod-1` as `PRIMARY` and `sql-prod-2` as `SECONDARY` with `is_read_replica = YES`.

Because `dba-lab` and `monitor` are separate Docker Compose projects on separate networks, point the fleet datasources at the published host ports rather than container names, e.g. `DB_HOST_PROD1=host.docker.internal,1403`.
