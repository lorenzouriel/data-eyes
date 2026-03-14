-- =============================================
-- Query: Largest Tables
-- Description: Shows table size (total, used, data) and row count
-- Data Source: sys.tables, sys.indexes, sys.partitions, sys.allocation_units
-- =============================================
SELECT  
    s.name AS schema_name,  
    t.name AS table_name,  
    p.rows AS row_count,  
    CONVERT(DECIMAL(18,2), SUM(a.total_pages) * 8 / 1024.0) AS total_size_mb,  
    CONVERT(DECIMAL(18,2), SUM(a.used_pages) * 8 / 1024.0) AS used_size_mb,  
    CONVERT(DECIMAL(18,2), SUM(a.data_pages) * 8 / 1024.0) AS data_size_mb  
FROM sys.tables t  
JOIN sys.indexes i ON t.object_id = i.object_id  
JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id  
JOIN sys.allocation_units a ON p.partition_id = a.container_id  
JOIN sys.schemas s ON t.schema_id = s.schema_id  
WHERE t.is_ms_shipped = 0  -- Ignore system tables
GROUP BY s.name, t.name, p.rows  
ORDER BY total_size_mb DESC;