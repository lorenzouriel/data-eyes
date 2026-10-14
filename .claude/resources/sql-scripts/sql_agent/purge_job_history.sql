/************************************************************************************************
-- Author:       Lorenzo Uriel
-- Created Date: 2025-08-19
-- Purpose:      Purge SQL Server Agent job history older than 30 days.
-- Description:  This script:
--                 1. Sets NOCOUNT ON to prevent extra result messages.
--                 2. Calculates the cutoff date (30 days before today).
--                 3. Executes the system stored procedure sp_purge_jobhistory 
--                    to delete job history records older than the cutoff date.
************************************************************************************************/

-- Prevent extra result messages from interfering with output
SET NOCOUNT ON;

-- ===============================================
-- Step 1: Declare variable to store cutoff date
-- ===============================================
DECLARE @CleanupDate DATETIME;

-- ===============================================
-- Step 2: Calculate date 30 days ago from today
-- ===============================================
SET @CleanupDate = DATEADD(DAY, -30, GETDATE());

-- ===============================================
-- Step 3: Execute system stored procedure to purge old job history
-- ===============================================
EXECUTE dbo.sp_purge_jobhistory 
    @oldest_date = @CleanupDate;