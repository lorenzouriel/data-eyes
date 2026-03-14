/*
================================================================================
SQL SERVER FIXED SERVER ROLES DOCUMENTATION
================================================================================
Author: Lorenzo Uriel
Date: 2025-08-20
Purpose: List all fixed server roles and their permissions for reference
================================================================================
*/

-- 1. sysadmin
-- Members of this role have **unrestricted access** to all server and database functions.
-- They can perform **any activity** in the SQL Server instance.
EXEC sp_srvrolepermission 'sysadmin';

-- 2. serveradmin
-- Members can configure server-wide settings and **shutdown the SQL Server instance**.
-- Permissions include changing configuration options and setting server-wide parameters.
EXEC sp_srvrolepermission 'serveradmin';

-- 3. setupadmin
-- Members can manage linked servers and extended stored procedures.
-- Typically used for **installation and setup tasks**.
EXEC sp_srvrolepermission 'setupadmin';

-- 4. securityadmin
-- Members manage server logins, their properties, and **permissions**.
-- They can also reset passwords for SQL logins.
EXEC sp_srvrolepermission 'securityadmin';

-- 5. processadmin
-- Members can **terminate SQL Server processes** using KILL.
EXEC sp_srvrolepermission 'processadmin';

-- 6. dbcreator
-- Members can **create, alter, drop, and restore databases**.
-- They cannot manage logins unless also part of securityadmin.
EXEC sp_srvrolepermission 'dbcreator';

-- 7. diskadmin
-- Members can manage **disk files** and allocate disk space for the SQL Server instance.
EXEC sp_srvrolepermission 'diskadmin';

-- 8. bulkadmin
-- Members can execute **bulk insert operations**.
-- They can use BULK INSERT to import data from files into tables.
EXEC sp_srvrolepermission 'bulkadmin';