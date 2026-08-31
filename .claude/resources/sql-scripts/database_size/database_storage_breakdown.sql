-- =============================================
-- Query: Database Storage Breakdown
-- Description: Calculates row, log, total sizes per database
-- Data Source: sys.master_files
-- =============================================
SELECT  
    DB_NAME() AS database_name,  
    CAST(SUM(CASE WHEN type_desc = 'LOG' THEN size END) * 8. / 1024 AS DECIMAL(8,2)) AS log_size_mb,  
    CAST(SUM(CASE WHEN type_desc = 'ROWS' THEN size END) * 8. / 1024 AS DECIMAL(8,2)) AS row_size_mb,  
    CONVERT(DECIMAL(18,2), SUM(size) * 8 / 1024.0) AS total_size_mb,  
    CONVERT(DECIMAL(18,2), SUM(size) * 8 / 1024.0 / 1024.0) AS total_size_gb  
FROM sys.master_files  
WHERE database_id = DB_ID()  
GROUP BY database_id;