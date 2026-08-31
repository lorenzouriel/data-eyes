/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Configure SQL Server Auditing for compliance and security monitoring
-- Description:  Sets up a server audit, database audit specification, and server audit specification
-- Notes:        Ensure the FILEPATH exists and SQL Server service account has write permission.
--               Auditing sensitive tables and login failures helps meet compliance requirements.
************************************************************************************************/

-- ============================================================
-- 1. CREATE SERVER AUDIT OBJECT
-- ============================================================
/*
Purpose:
  - Central audit object to collect audit events.
  - Logs are stored in a secure folder with access restrictions.
Parameters:
  - FILEPATH: Folder where audit logs are saved.
  - MAXSIZE: Maximum file size before rollover.
  - MAX_ROLLOVER_FILES: Maximum number of rolled-over files to keep (~90 days retention).
  - ON_FAILURE: Action if audit cannot write (CONTINUE avoids blocking SQL operations).
*/
CREATE SERVER AUDIT FinPulseComplianceAudit
TO FILE (
    FILEPATH = 'E:\FinPulse_AuditLogs\',  -- Must exist & have restricted access
    MAXSIZE = 500 MB,
    MAX_ROLLOVER_FILES = 50               -- ~90 days retention before rotation
)
WITH (ON_FAILURE = CONTINUE);

-- Enable the audit
ALTER SERVER AUDIT FinPulseComplianceAudit
WITH (STATE = ON);

-- ============================================================
-- 2. CREATE DATABASE AUDIT SPECIFICATION
-- ============================================================
/*
Purpose:
  - Track SELECT, UPDATE, DELETE operations on sensitive tables.
Database Context:
  - Must switch to the target database (Transactions in this case).
Parameters:
  - ADD (...): Specifies which actions and objects to audit.
  - BY PUBLIC: Applies to all users.
  - STATE = ON: Activates the specification immediately.
*/
USE Transactions;
GO

CREATE DATABASE AUDIT SPECIFICATION AuditCustomerAccountAccess
FOR SERVER AUDIT FinPulseComplianceAudit
ADD (SELECT, UPDATE, DELETE ON dbo.CustomerAccounts BY PUBLIC)
WITH (STATE = ON);

-- ============================================================
-- 3. CREATE SERVER AUDIT SPECIFICATION
-- ============================================================
/*
Purpose:
  - Track server-level events such as failed login attempts.
Parameters:
  - FAILED_LOGIN_GROUP: Captures all failed login attempts on the SQL Server instance.
  - STATE = ON: Activates the specification immediately.
*/
CREATE SERVER AUDIT SPECIFICATION AuditFailedLogins
FOR SERVER AUDIT FinPulseComplianceAudit
ADD (FAILED_LOGIN_GROUP)
WITH (STATE = ON);
GO