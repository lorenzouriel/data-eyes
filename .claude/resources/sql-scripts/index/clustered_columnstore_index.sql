-- =============================================
-- CLUSTERED COLUMNSTORE INDEX
-- PURPOSE: Store data in column-oriented format for analytics
-- NOTES:
-- - Drop existing clustered index if present
-- - Useful for aggregations on large datasets
-- =============================================
CREATE CLUSTERED COLUMNSTORE INDEX cix_YourTable_Columnstore
ON YourTable
WITH (DROP_EXISTING = ON);