-- =============================================
-- NONCLUSTERED INDEX (single/multiple columns)
-- PURPOSE: Create nonclustered index on 'name' and 'date' columns
-- NOTES:
-- - Nonclustered indexes point to rows without changing physical order
-- - Can have multiple nonclustered indexes per table
-- =============================================
CREATE NONCLUSTERED INDEX ncix_YourTable_Name_Date
ON YourTable(name DESC, date DESC);