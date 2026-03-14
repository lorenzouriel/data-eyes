/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Monitor and optionally terminate SQL Server Agent sessions.
-- Description:  This script retrieves information about currently running sessions initiated
--               by SQL Server Agent jobs. It can help identify long-running or stuck jobs.
-- Note:         Use the KILL command with caution; terminating a session may cause rollback
--               and affect ongoing processes.
************************************************************************************************/

-- ============================================================
-- Retrieve running SQL Server Agent sessions
-- ============================================================
SELECT 
    r.session_id,          -- ID of the request/session
    r.start_time,          -- When the request started
    r.status,              -- Current status (running, suspended, etc.)
    r.command,             -- Type of command being executed
    t.text AS sql_text,    -- SQL text of the command
    s.program_name,        -- Program that initiated the session (SQLAgent)
    s.login_name,          -- Login name of the user executing the session
    s.host_name            -- Host machine of the session
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s 
    ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE s.program_name LIKE 'SQLAgent%'; -- Filters sessions started by SQL Server Agent

-- ============================================================
-- Optionally terminate a session
-- ============================================================
-- Replace <session_id> with the actual session_id from the query above.
-- WARNING: KILL will terminate the session, which may cause rollback and impact running jobs.
-- Example: KILL 52;
KILL <session_id>;  
