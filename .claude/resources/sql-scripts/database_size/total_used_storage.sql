-- =============================================
-- Query: Total Storage Used
-- Description: Calculates total allocated storage across all databases
-- Data Source: sys.master_files
-- Units: MB and GB
-- =============================================
SELECT  
    SUM(CAST(size AS BIGINT)) * 8 / 1024 AS total_size_mb,  
    SUM(CAST(size AS BIGINT)) * 8 / 1024.0 / 1024.0 AS total_size_gb  
FROM sys.master_files;