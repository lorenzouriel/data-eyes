-- #######################
-- CHECKDB STALENESS + SUSPECT PAGES — live observation, read-only
-- Purpose: "Is there corruption, and when did we last check" — the query
--          maintenance/ never had (only action scripts existed before).
-- Prerequisite: reads master.dbo.CommandLog, which only exists once Ola
--               Hallengren's maintenance scripts are installed (see
--               maintenance/README.md). Databases never CHECKDB'd via that
--               path show LastCheckDBEndTime = NULL and severity CRITICAL.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> maintenance.checkdb
-- Params: @DatabaseName = NULL checks all user databases; set it to check one.
-- #######################

DECLARE @DatabaseName NVARCHAR(128) = NULL;

;WITH LastCheck AS (
    SELECT
        DatabaseName,
        MAX(EndTime) AS LastCheckDBEndTime
    FROM master.dbo.CommandLog
    WHERE CommandType LIKE '%CHECK%'
    GROUP BY DatabaseName
),
SuspectPages AS (
    SELECT database_id, COUNT(*) AS SuspectPageCount
    FROM msdb.dbo.suspect_pages
    WHERE event_type IN (1, 2, 3)  -- 823/824/repair-related; excludes event_type=4 (cleared)
    GROUP BY database_id
),
Base AS (
    SELECT
        d.name AS DatabaseName,
        lc.LastCheckDBEndTime,
        DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) AS DaysSinceLastCheckDB,
        ISNULL(sp.SuspectPageCount, 0) AS SuspectPageCount,
        CASE
            WHEN ISNULL(sp.SuspectPageCount, 0) > 0 THEN 'CRITICAL'
            WHEN lc.LastCheckDBEndTime IS NULL THEN 'CRITICAL'
            WHEN DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) >= 14 THEN 'CRITICAL'
            WHEN DATEDIFF(DAY, lc.LastCheckDBEndTime, GETDATE()) >= 7 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.databases d
    LEFT JOIN LastCheck lc ON lc.DatabaseName = d.name
    LEFT JOIN SuspectPages sp ON sp.database_id = d.database_id
    WHERE d.database_id > 4
        AND d.state_desc = 'ONLINE'
        AND (@DatabaseName IS NULL OR d.name = @DatabaseName)
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, DaysSinceLastCheckDB DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
