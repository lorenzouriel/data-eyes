-- =============================================
-- SCRIPT: CREATE CREDENTIAL AND SQL AGENT PROXY
-- PURPOSE: Create a Windows credential and a SQL Server Agent proxy
--          to allow jobs or SSIS packages to run under a specific Windows account
-- NOTES:
-- - CREDENTIAL stores Windows authentication info (username + password)
-- - PROXY allows SQL Server Agent jobs to execute with this credential
-- =============================================

-- Step 1: Switch to the master database (credentials are created in master)
USE master;
GO

-- Step 2: Create a new credential
CREATE CREDENTIAL [ProxyCredentialAdmin]
WITH IDENTITY = 'WIN-COMPUTER\User',                 -- Windows account to run jobs
     SECRET = 'PasswordProxy';                -- Password for the Windows account
GO

-- Step 3: Switch to msdb database (SQL Agent jobs and proxies are managed here)
USE msdb;
GO

-- Step 4: Create a new SQL Server Agent proxy
EXEC dbo.sp_add_proxy  
    @proxy_name = 'AdminProxy',                     -- Name of the proxy
    @credential_name = 'ProxyCredentialAdmin',     -- Associate the proxy with the credential created above
    @enabled = 1;                                  -- Enable the proxy immediately
GO

-- After this, you can assign the proxy to job steps, SSIS packages, or other SQL Agent operations