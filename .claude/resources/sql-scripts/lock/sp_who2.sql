----------------------------------------------------------
-- Basic Active Sessions Overview
----------------------------------------------------------
-- Description: Uses the built-in stored procedure sp_who2
-- to show all current sessions, their status, CPU usage, I/O,
-- and if they are being blocked.
-- Useful for a quick check of active connections.

USE [master];
GO

EXEC sp_who2;
GO