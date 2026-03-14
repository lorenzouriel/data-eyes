-- ============================================
-- List all reports under the '/Reports' folder
-- ============================================

SELECT *
FROM [dbo].[Catalog]
WHERE [Path] LIKE '%/Reports%';


-- ============================================
-- List all data sources used by reports
--    Only consider reports under '/Reports'
-- ============================================

SELECT *
FROM [dbo].[DataSource]
WHERE [ItemID] IN (
    SELECT [ItemID]
    FROM [dbo].[Catalog]
    WHERE [Path] LIKE '%/Reports%'
);