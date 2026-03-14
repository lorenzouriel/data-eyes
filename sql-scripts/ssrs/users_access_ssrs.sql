/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-20
-- Purpose:      Retrieve all user accounts from the ReportServer database.
-- Description:  This query selects all users from the dbo.Users table, including their
--               unique ID, username, user type, authentication type, and the date when
--               the user record was last modified.
************************************************************************************************/
SELECT
    Users.UserID,
    Users.UserName,
    Users.UserType,
    Users.AuthType,
    Users.ModifiedDate
FROM dbo.Users;