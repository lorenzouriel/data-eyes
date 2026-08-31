/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-20
-- Purpose:      Retrieve catalog items with their details and parent information.
-- Description:  This query selects all items from the catalog, including reports, folders,
--               files, linked reports, data sources, report models, KPIs, shared datasets,
--               mobile reports, and PowerBI documents. It joins the catalog to itself to
--               include the parent item name. The item type is mapped from its numeric code
--               to a descriptive label. Additional details include description, hidden flag,
--               creation and modification dates, and content size.
************************************************************************************************/
SELECT
    CHILD_ITEM.Path AS Item_Path,
    CHILD_ITEM.Name AS Item_Name,
    CASE
        WHEN CHILD_ITEM.Type = 1 THEN 'Folder (1)'
        WHEN CHILD_ITEM.Type = 2 THEN 'Report (2)'
        WHEN CHILD_ITEM.Type = 3 THEN 'File (3)'
        WHEN CHILD_ITEM.Type = 4 THEN 'Linked Report (4)'
        WHEN CHILD_ITEM.Type = 5 THEN 'Data Source (5)'
        WHEN CHILD_ITEM.Type = 6 THEN 'Report Model (6)'
        WHEN CHILD_ITEM.Type = 7 THEN 'Report Part (7)'
        WHEN CHILD_ITEM.Type = 8 THEN 'Shared Data Set (8)'
        WHEN CHILD_ITEM.Type = 9 THEN 'Report Part (9)'
        WHEN CHILD_ITEM.Type = 11 THEN 'KPI (11)'
        WHEN CHILD_ITEM.Type = 12 THEN 'Mobile Report Folder (12)'
        WHEN CHILD_ITEM.Type = 13 THEN 'PowerBI Desktop Document (13)'
    END AS Item_Type,
    PARENT_ITEM.Name AS Parent_Item_Name,
    CHILD_ITEM.Description AS Item_Description,
    CHILD_ITEM.Hidden AS Is_Hidden,
    CHILD_ITEM.CreationDate,
    CHILD_ITEM.ModifiedDate,
    CHILD_ITEM.ContentSize
FROM dbo.Catalog CHILD_ITEM
LEFT JOIN dbo.Catalog PARENT_ITEM
    ON PARENT_ITEM.ItemID = CHILD_ITEM.ParentID;
