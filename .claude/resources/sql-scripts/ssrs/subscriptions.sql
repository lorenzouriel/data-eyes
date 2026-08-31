/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-20
-- Purpose:      Retrieve detailed information about report subscriptions.
-- Description:  This query joins the Subscriptions table with Users and Catalog tables to
--               provide comprehensive details about each subscription. It includes the
--               subscription description, last status, event type, last run time, parameters,
--               subscription owner, associated report name, the user who last modified the
--               subscription, and the modification date.
************************************************************************************************/
SELECT
    Subscriptions.Description,
    Subscriptions.LastStatus,
    Subscriptions.EventType,
    Subscriptions.LastRunTime,
    Subscriptions.Parameters,
    SUBSCRIPTION_OWNER.UserName AS SubscriptionOwner,
    Catalog.Name AS ReportName,
    MODIFIED_BY.UserName AS LastModifiedBy,
    Subscriptions.ModifiedDate
FROM dbo.Subscriptions
INNER JOIN dbo.Users SUBSCRIPTION_OWNER
    ON SUBSCRIPTION_OWNER.UserID = Subscriptions.OwnerID
INNER JOIN dbo.Catalog
    ON Catalog.ItemID = Subscriptions.Report_OID
INNER JOIN dbo.Users MODIFIED_BY
    ON MODIFIED_BY.UserID = Subscriptions.ModifiedByID;