-- ================================================
-- Table to store median and quartiles
-- ================================================
CREATE TABLE [dbo].[median]
(
    id INT IDENTITY(1,1) NOT NULL,
    [user_id] INT NULL,
    median FLOAT NULL,
    q1 FLOAT NULL,
    q3 FLOAT NULL
);
GO

-- ================================================
-- Inspect all SLA records for a specific user
-- ================================================
SELECT *
FROM [dbo].[sla]
WHERE [user_id] = 80000;
GO

-- ================================================
-- Inspect SLA records for a specific user ordered by points
-- ================================================
SELECT *
FROM [dbo].[sla]
WHERE [user_id] = 80000
ORDER BY [tot_points];
GO

-- ================================================
-- Inspect stored median records for a specific user
-- ================================================
SELECT *
FROM [dbo].[median]
WHERE [user_id] = 80000;
GO

-- ================================================
-- Calculate median, Q1 (25th percentile), Q3 (75th percentile)
-- ================================================
SELECT TOP 1
    [user_id],
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tot_points) OVER () AS median,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY tot_points) OVER () AS q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY tot_points) OVER () AS q3
FROM [dbo].[sla]
WHERE [user_id] = 80000;
GO

-- ================================================
-- Calculate only the median for a specific user
-- ================================================
SELECT TOP 1
    [user_id],
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tot_points) OVER () AS median
FROM [dbo].[sla]
WHERE [user_id] = 80000;
GO

-- ================================================
-- Optional: Insert calculated median and quartiles into [median] table
-- ================================================
INSERT INTO [dbo].[median] ([user_id], median, q1, q3)
SELECT TOP 1
    [user_id],
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tot_points) OVER () AS median,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY tot_points) OVER () AS q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY tot_points) OVER () AS q3
FROM [dbo].[sla]
WHERE [user_id] = 80000;
GO