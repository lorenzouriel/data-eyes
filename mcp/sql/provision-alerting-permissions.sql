/*
  Optional permissions for the dashboard's alert catalog (docs/features/alerts.md).
  Review every grant. Do not execute this template unchanged in production.

  The monitoring login from provision-readonly-login.sql (VIEW SERVER STATE)
  already covers most alerts. Each section below enables specific alerts; skip
  a section and turn those alerts off on the Alerts page instead.

  Example: sqlcmd -S <server> -v LoginName="data_eyes_monitor" -i provision-alerting-permissions.sql
*/
USE [master];
GO

-- Sysadmin Membership Changed, New Login Created, sa Login Enabled,
-- Certificate Expiry, Stale Statistics, Identity Values / Int-Bigint Limit.
-- Lets the login read metadata (not data) of every object on the server.
GRANT VIEW ANY DEFINITION TO [$(LoginName)];
GO

-- Database Corruption and Rebuild Failed read Ola Hallengren's CommandLog.
IF USER_ID(N'$(LoginName)') IS NULL
    CREATE USER [$(LoginName)] FOR LOGIN [$(LoginName)];
GO
IF OBJECT_ID(N'dbo.CommandLog') IS NOT NULL
    GRANT SELECT ON dbo.CommandLog TO [$(LoginName)];
GO

USE [msdb];
GO

IF USER_ID(N'$(LoginName)') IS NULL
    CREATE USER [$(LoginName)] FOR LOGIN [$(LoginName)];
GO

-- DB Without Full Backup, DB Without Log Backup, New Database Not Covered.
GRANT SELECT ON dbo.backupset TO [$(LoginName)];
-- Page Corruption.
GRANT SELECT ON dbo.suspect_pages TO [$(LoginName)];
-- Job Failed, Job Disabled or Deleted.
GRANT SELECT ON dbo.sysjobs TO [$(LoginName)];
GRANT SELECT ON dbo.sysjobhistory TO [$(LoginName)];
GRANT EXECUTE ON dbo.agent_datetime TO [$(LoginName)];
-- Log Shipping Latency.
GRANT SELECT ON dbo.log_shipping_monitor_primary TO [$(LoginName)];
GRANT SELECT ON dbo.log_shipping_monitor_secondary TO [$(LoginName)];
GO

/*
  HIGHER-PRIVILEGE GRANTS — left commented out on purpose.

  Slow File Growth reads the default trace. ALTER TRACE also allows the login
  to create server traces, which can capture query text and parameters.

  USE [master];
  GRANT ALTER TRACE TO [$(LoginName)];

  Backup Failed, I/O Errors 823/824/825, Database Errors and Login Failed read
  the error log with xp_readerrorlog, which SQL Server only allows for
  securityadmin members. securityadmin can grant itself further permissions,
  so treat it as close to sysadmin. Prefer a dedicated, tightly held login, or
  leave those four alerts off.

  ALTER SERVER ROLE [securityadmin] ADD MEMBER [$(LoginName)];
*/
