----------------------------------------------------------
-- Detailed Blocking Sessions Report
----------------------------------------------------------
-- Description: Queries system DMVs to identify sessions that are 
-- being blocked and the sessions that are blocking them.
-- Provides more detail than sp_who2, including executing query text.

SELECT
    r.session_id,                 -- ID of the session currently waiting
    r.blocking_session_id,        -- ID of the session causing the block
    r.status,                     -- Status of the blocked session
    r.command,                    -- Command being executed
    r.wait_type,                  -- Type of wait (e.g., locks)
    r.wait_time,                  -- Time the session has been waiting in ms
    r.wait_resource,              -- Resource being waited on
    t.text AS query_text,         -- Text of the SQL query being executed
    s.host_name,                  -- Client machine name
    s.program_name,               -- Application name
    s.login_name                  -- Login executing the session
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s 
    ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.blocking_session_id <> 0 -- Only show sessions that are blocked
ORDER BY r.wait_time DESC;        -- Order by longest waiting sessions first
