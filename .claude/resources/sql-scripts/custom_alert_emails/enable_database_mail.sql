-- =============================================
-- PURPOSE: Enable Database Mail to allow SQL Server
--          to send emails programmatically
-- =============================================
EXEC sp_configure 'show advanced options', 1;  -- Allow changing advanced settings
RECONFIGURE;  

EXEC sp_configure 'Database Mail XPs', 1;     -- Enable Database Mail extended stored procedures
RECONFIGURE;

-- =============================================
-- CHECK YOUR DATABASE MAIL PROFILE  
SELECT 
	*
FROM msdb.dbo.sysmail_profile;