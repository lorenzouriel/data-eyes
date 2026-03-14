-- ========================================================
-- Check the last executed command for a specific session
-- ========================================================
-- Replace 225 with the session_id you want to inspect.
-- DBCC INPUTBUFFER shows the last statement executed by a session.
DBCC INPUTBUFFER(225);