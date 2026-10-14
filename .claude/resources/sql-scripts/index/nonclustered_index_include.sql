-- =============================================
-- NONCLUSTERED INDEX WITH INCLUDE
-- PURPOSE: Optimize queries using 'name' and 'phone'
-- NOTES:
-- - INCLUDE columns are stored in index for direct query access
-- - Avoids reading main table if query uses indexed and included columns
-- =============================================
CREATE NONCLUSTERED INDEX ncix_YourTable_Name_Include
ON YourTable(name)
INCLUDE (phone);