/************************************************************************************************
-- Purpose:      Grant SQL Server Agent roles to a specific user.
-- Description:  This script demonstrates how to add a user to different SQL Server Agent roles:
--                 1. SQLAgentReaderRole   - View jobs and their status (read-only).
--                 2. SQLAgentOperatorRole - View, execute jobs, and read logs.
--                 3. SQLAgentUserRole     - Create and modify own jobs only.
-- Note:         Replace 'username' with the actual SQL Server login.
************************************************************************************************/

-- ============================================================
-- Grant SQL Server Agent Reader Role
-- Purpose: Allows the user to view all SQL Server Agent jobs and their status.
-- ============================================================
USE [msdb];
GO
EXEC sp_addrolemember N'SQLAgentReaderRole', N'username';
GO

-- ============================================================
-- Grant SQL Server Agent Operator Role
-- Purpose: Allows the user to view and execute jobs, and read job history/logs.
-- ============================================================
USE [msdb];
GO
EXEC sp_addrolemember N'SQLAgentOperatorRole', N'username';
GO

-- ============================================================
-- Grant SQL Server Agent User Role
-- Purpose: Allows the user to create and modify their own jobs but not others' jobs.
-- ============================================================
USE [msdb];
GO
EXEC sp_addrolemember N'SQLAgentUserRole', N'username';
GO