-- #######################
-- BLOCKING CHAIN SNAPSHOT — live observation, read-only, instance-wide
-- Purpose: Point-in-time snapshot of active blocking, with head-blocker
--          identification, for the Sessions/Blocking tab and Step 3
--          (Contention) of the performance methodology.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> waits.blocking_duration_seconds
-- Note: this is a snapshot, not a trend — run repeatedly to see if a chain
--       persists, or to catch transient blocking, it must be running.
-- #######################

;WITH Blocking AS (
    SELECT
        r.session_id AS BlockedSessionID,
        r.blocking_session_id AS BlockingSessionID,
        r.wait_type AS WaitType,
        r.wait_time / 1000.0 AS WaitTimeSeconds,
        r.wait_resource AS WaitResource,
        DB_NAME(r.database_id) AS DatabaseName,
        s.login_name AS BlockedLoginName,
        s.host_name AS BlockedHostName,
        st.text AS BlockedQueryText,
        CASE
            WHEN r.blocking_session_id NOT IN (
                SELECT session_id FROM sys.dm_exec_requests WHERE blocking_session_id <> 0
            ) THEN 1 ELSE 0
        END AS BlockingSessionIsHeadBlocker,
        CASE
            WHEN r.wait_time / 1000.0 >= 120 THEN 'CRITICAL'
            WHEN r.wait_time / 1000.0 >= 30 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
    OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st
    WHERE r.blocking_session_id <> 0
        AND r.blocking_session_id <> r.session_id
)
SELECT *
FROM Blocking
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, WaitTimeSeconds DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
