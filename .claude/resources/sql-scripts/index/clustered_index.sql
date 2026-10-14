-- =============================================
-- CLUSTERED INDEX
-- PURPOSE: Create clustered index on 'id' column in descending order
-- NOTES:
-- - Determines the physical order of data in the table
-- - Only one clustered index per table
-- =============================================
CREATE CLUSTERED INDEX cix_YourTable_Id
ON YourTable(id DESC);