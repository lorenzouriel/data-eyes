/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-20
-- Purpose:      Retrieve catalog items along with associated users and roles.
-- Description:  This query joins the ReportServer catalog, users, policy-user-role, and roles
--               tables to produce a list of all catalog items with their type, path, and name,
--               along with each user and their assigned role and role description. The item type
--               numeric codes are mapped to descriptive labels. Results are ordered by item type,
--               item name, and username.
************************************************************************************************/
SELECT
    CASE
        WHEN catalog.Type = 1 THEN 'Folder (1)'
        WHEN catalog.Type = 2 THEN 'Report (2)'
        WHEN catalog.Type = 3 THEN 'File (3)'
        WHEN catalog.Type = 4 THEN 'Linked Report (4)'
        WHEN catalog.Type = 5 THEN 'Data Source (5)'
        WHEN catalog.Type = 6 THEN 'Report Model (6)'
        WHEN catalog.Type = 7 THEN 'Report Part (7)'
        WHEN catalog.Type = 8 THEN 'Shared Data Set (8)'
        WHEN catalog.Type = 9 THEN 'Report Part (9)'
        WHEN catalog.Type = 11 THEN 'KPI (11)'
        WHEN catalog.Type = 12 THEN 'Mobile Report Folder (12)'
        WHEN catalog.Type = 13 THEN 'PowerBI Desktop Document (13)'
    END AS Item_Type,
    catalog.Path,
    catalog.Name,
    users.UserName,
    roles.RoleName,
    roles.Description
FROM ReportServer.dbo.users
INNER JOIN ReportServer.dbo.policyuserrole
    ON users.userid = policyuserrole.userid
INNER JOIN ReportServer.dbo.roles
    ON roles.roleid = policyuserrole.roleid
INNER JOIN ReportServer.dbo.catalog
    ON catalog.policyid = policyuserrole.policyid
ORDER BY catalog.Type, catalog.Name, users.UserName;