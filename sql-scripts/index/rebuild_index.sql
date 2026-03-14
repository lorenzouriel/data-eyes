-- =============================================
-- REBUILD INDEX
-- PURPOSE: Remove fragmentation completely and recreate index
-- NOTES:
-- - Use for high fragmentation or after bulk operations
-- - Resource intensive, may lock table
-- =============================================
ALTER INDEX cix_YourTable_Id ON [YourTable] REBUILD;             -- Clustered
ALTER INDEX ncix_YourTable_Name_Date ON [YourTable] REBUILD;    -- Nonclustered
ALTER INDEX ALL ON [YourTable] REBUILD;                        -- All indexes