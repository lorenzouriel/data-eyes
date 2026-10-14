-- =============================================
-- NONCLUSTERED COLUMNSTORE INDEX
-- PURPOSE: Create columnstore index on selected columns for DW/analytics
-- NOTES:
-- - Can include multiple columns
-- - Optional DROP_EXISTING for replacement
-- =============================================
CREATE NONCLUSTERED COLUMNSTORE INDEX ncix_YourTable_Name_Date_Columnstore
ON YourTable(name, date);