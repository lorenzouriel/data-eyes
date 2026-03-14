-- =============================================
-- Script: Database Storage Alert
-- Description: Checks total, used, max size and raises warnings/alerts
-- Author: Lorenzo Uriel
-- Date: 2025-08-19
-- =============================================
DECLARE @db_name SYSNAME = DB_NAME();  
DECLARE @total_size_mb DECIMAL(18,2);  
DECLARE @used_size_mb DECIMAL(18,2);  
DECLARE @max_size_mb DECIMAL(18,2);  
DECLARE @usage_pct DECIMAL(5,2);  
DECLARE @usage_pct_str VARCHAR(10);  
  
-- Get total and used sizes for current DB  
SELECT  
    @total_size_mb = SUM(size) * 8.0 / 1024,  
    @used_size_mb = SUM(CASE WHEN type_desc = 'ROWS' THEN size END) * 8.0 / 1024  
FROM sys.master_files  
WHERE database_id = DB_ID();  
  
-- Get max size (customize unlimited values)  
SELECT @max_size_mb =  
    MAX(CASE  
        WHEN max_size = -1 THEN 2000  -- Example for unlimited files
        ELSE max_size * 8.0 / 1024  
    END)  
FROM sys.database_files;  
  
-- Calculate usage percentage  
SET @usage_pct = (@total_size_mb / @max_size_mb) * 100;  
SET @usage_pct_str = CAST(@usage_pct AS VARCHAR(10));  
  
-- Print status  
PRINT 'Database: ' + @db_name;  
PRINT 'Used: ' + CAST(@used_size_mb AS VARCHAR) + ' MB';  
PRINT 'Total: ' + CAST(@total_size_mb AS VARCHAR) + ' MB';  
PRINT 'Max: ' + CAST(@max_size_mb AS VARCHAR) + ' MB';  
PRINT 'Usage: ' + @usage_pct_str + '%';  
  
-- Raise alerts  
IF @usage_pct >= 80 AND @usage_pct < 90  
    RAISERROR('Warning: Database "%s" is %s%% full.', 16, 1, @db_name, @usage_pct_str);  

IF @usage_pct >= 90 AND @usage_pct < 95  
    RAISERROR('High Warning: Database "%s" is %s%% full.', 16, 1, @db_name, @usage_pct_str);  

IF @usage_pct >= 95 AND @usage_pct < 99  
    RAISERROR('Critical: Database "%s" is %s%% full. Consider cleanup or expansion.', 16, 1, @db_name, @usage_pct_str);  

IF @usage_pct >= 99  
    RAISERROR('EMERGENCY: Database "%s" is %s%% full. Immediate action required!', 16, 1, @db_name, @usage_pct_str);

-- Example custom max size
-- SELECT @max_size_mb = 1800;  -- MB