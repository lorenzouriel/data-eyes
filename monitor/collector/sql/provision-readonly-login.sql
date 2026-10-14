/*
  Review every grant. Do not execute this template unchanged in production.
*/
USE [master];
GO

IF SUSER_ID(N'$(LoginName)') IS NULL
BEGIN
    DECLARE @create_login nvarchar(max) =
        N'CREATE LOGIN ' + QUOTENAME(N'$(LoginName)') +
        N' WITH PASSWORD = ' + QUOTENAME(N'$(Password)', '''') +
        N', CHECK_POLICY = ON, CHECK_EXPIRATION = ON;';
    EXEC sys.sp_executesql @create_login;
END;
GO

-- Required by instance-level diagnostic tools. Remove this grant and those
-- tools from instances.yaml when the deployment only needs application data.
GRANT VIEW SERVER STATE TO [$(LoginName)];
GO

USE [$(DatabaseName)];
GO

IF USER_ID(N'$(LoginName)') IS NULL
    CREATE USER [$(LoginName)] FOR LOGIN [$(LoginName)];
GO

GRANT CONNECT TO [$(LoginName)];
GRANT SELECT ON SCHEMA::[$(SchemaName)] TO [$(LoginName)];
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, CONTROL TO [$(LoginName)];
GO

/*
  Optional SQL Server Resource Governor outline (Enterprise/server-wide).
  A DBA must choose workload limits and a classifier appropriate to the site:

  CREATE RESOURCE POOL data_eyes_mcp_pool
    WITH (MAX_CPU_PERCENT = 10, MAX_MEMORY_PERCENT = 10);
  CREATE WORKLOAD GROUP data_eyes_mcp_group
    USING data_eyes_mcp_pool
    WITH (REQUEST_MAX_CPU_TIME_SEC = 30, GROUP_MAX_REQUESTS = 8);

  Classify ORIGINAL_LOGIN() = '$(LoginName)' into data_eyes_mcp_group, then:
  ALTER RESOURCE GOVERNOR RECONFIGURE;
*/
