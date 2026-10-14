-- =============================================
-- PURPOSE: Delete all data from all tables in the database
-- while temporarily disabling constraints to avoid FK violations.
-- 
-- NOTES:
-- - Uses sp_msforeachtable to iterate over all tables
-- - Disables constraints before deletion and re-enables afterward
-- - QUOTED_IDENTIFIER is ON to allow quoted identifiers
-- =============================================

-- Step 1: Ensure QUOTED_IDENTIFIER is ON
-- This allows identifiers to be delimited by double quotes
SET QUOTED_IDENTIFIER ON;

-- Step 2: Disable all constraints on all tables
-- NOCHECK prevents SQL Server from checking existing data during the operation
EXEC sp_msforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL';

-- Step 3: Delete all data from every table
-- Each table is iterated and all rows are deleted
EXEC sp_msforeachtable '
    SET QUOTED_IDENTIFIER ON;      -- Ensure QUOTED_IDENTIFIER is ON for each execution
    DELETE FROM ?;                 -- Delete all rows from the current table
';

-- Step 4: Re-enable constraints on all tables
-- WITH CHECK ensures that constraints are validated against the data
EXEC sp_msforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL';