-- =============================================
-- PURPOSE: Retrieve key SQL Server instance properties
-- =============================================

-- Step 1: Basic instance information
SELECT 
    SERVERPROPERTY('InstanceName') AS InstanceName,   -- Name of the SQL Server instance
    SERVERPROPERTY('Edition') AS Edition,             -- SQL Server edition (e.g., Standard, Enterprise)
    SERVERPROPERTY('ProductVersion') AS Version,     -- Full product version number
    SERVERPROPERTY('InstallDate') AS InstallDate,    -- Installation date of this instance
    SERVERPROPERTY('ServerName') AS ServerName,      -- SQL Server network name
    SERVERPROPERTY('MachineName') AS MachineName,    -- Physical machine name
    SERVERPROPERTY('SqlBinRoot') AS SqlBinRoot       -- Path to SQL Server binaries

-- Step 2: Default file locations for new databases
SELECT 
    SERVERPROPERTY('InstanceDefaultDataPath') AS DefaultDataPath,   -- Default path for data files
    SERVERPROPERTY('InstanceDefaultLogPath') AS DefaultLogPath;     -- Default path for log files
