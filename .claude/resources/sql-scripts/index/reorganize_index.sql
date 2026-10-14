-- =============================================
-- REORGANIZE INDEX
-- PURPOSE: Light-weight index maintenance
-- NOTES:
-- - Reorganizes index pages without full rebuild
-- - Keeps index online, low resource impact
-- =============================================
ALTER INDEX cix_YourTable_Id ON [YourTable] REORGANIZE;          -- Clustered
ALTER INDEX ncix_YourTable_Name_Date ON [YourTable] REORGANIZE;  -- Nonclustered
ALTER INDEX ALL ON [YourTable] REORGANIZE;                      -- All indexes