-- =============================================
-- PURPOSE: Check and configure SQL Server memory settings
-- =============================================

-- Enable advanced options to allow memory configuration changes
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;

-- Display current configuration values for min and max server memory
EXEC sp_configure 'min server memory (MB)';  -- Minimum memory SQL Server can use
EXEC sp_configure 'max server memory (MB)';  -- Maximum memory SQL Server can use

-- Check actual system memory usage
SELECT 
    total_physical_memory_kb / 1024 AS total_physical_memory_MB,     -- Total RAM available on the server
    available_physical_memory_kb / 1024 AS available_physical_memory_MB, -- Free RAM currently available
    total_page_file_kb / 1024 AS total_page_file_MB,                 -- Total page file size
    available_page_file_kb / 1024 AS available_page_file_MB,         -- Free page file size
    system_memory_state_desc                                          -- Overall memory state description
FROM sys.dm_os_sys_memory;

-- Change the SQL Server maximum memory limit to 4096 MB (4 GB)
EXEC sp_configure 'max server memory (MB)', 4096;
RECONFIGURE;

-- Change the SQL Server minimum memory limit to 1024 MB (1 GB)
EXEC sp_configure 'min server memory (MB)', 1024;
RECONFIGURE;
