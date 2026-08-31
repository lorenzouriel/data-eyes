/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Audit changes to the 'users' table for compliance and security monitoring
-- Description:  Creates a server audit object, a database audit specification for tracking
--               INSERT, UPDATE, DELETE operations on dbo.users, and enables them.
-- Notes:        Ensure the audit folder exists and SQL Server service account has write permission.
************************************************************************************************/

-- ============================================================
-- 1. CREATE SERVER AUDIT OBJECT
-- ============================================================
/*
Purpose:
  - Central audit object to collect database audit events.
Parameters:
  - FILEPATH: Folder where audit logs are saved (must exist & be write-protected)
  - MAXSIZE: Maximum file size before rollover
  - ROLLOVER: ON enables automatic file rollover when max size is reached
*/
CREATE SERVER AUDIT Audit_Users
TO FILE (
    FILEPATH = 'C:\AuditLogs\',  
    MAXSIZE = 10 MB,               
    ROLLOVER = ON
);

-- Enable the audit
ALTER SERVER AUDIT Audit_Users
WITH (STATE = ON);

-- ============================================================
-- 2. CREATE DATABASE AUDIT SPECIFICATION
-- ============================================================
/*
Purpose:
  - Tracks INSERT, UPDATE, DELETE operations on dbo.users table
Database Context:
  - Switch to the target database
Parameters:
  - ADD (...): Specifies actions and objects to audit
  - BY PUBLIC: Applies to all users
  - STATE = ON: Activates the specification immediately
*/
USE [database];
GO

CREATE DATABASE AUDIT SPECIFICATION Audit_Users_Changes
FOR SERVER AUDIT Audit_Users
ADD (INSERT, UPDATE, DELETE ON [dbo].[users] BY PUBLIC);
GO

-- Enable the database audit specification
ALTER DATABASE AUDIT SPECIFICATION Audit_Users_Changes
WITH (STATE = ON);
GO