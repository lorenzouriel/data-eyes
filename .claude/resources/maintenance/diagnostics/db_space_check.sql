-- #######################
-- DATABASE SPACE & DRIVE FREE SPACE — live observation, read-only
-- Purpose: Closes the "Storage" gap — this logic previously only existed as
--          inline Grafana panel SQL and prose in
--          monitor/docs/database_space_usage.md ("Database size per
--          database" panel). Per-file size/free-space plus underlying drive
--          free space, since a database can have plenty of free space
--          inside its files while the drive hosting them is nearly full.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> storage.drive_free_space_gb
-- Params: @DatabaseName = NULL checks all user databases; set it to check one.
-- #######################

DECLARE @DatabaseName NVARCHAR(128) = NULL;

;WITH Base AS (
    SELECT
        db.name AS DatabaseName,
        mf.name AS FileName,
        mf.type_desc AS FileType,
        CAST(mf.size * 8.0 / 1024 AS DECIMAL(18, 2)) AS FileSizeMB,
        CAST((mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) * 8.0 / 1024 AS DECIMAL(18, 2)) AS FreeSpaceMB,
        CAST(100.0 * (mf.size - FILEPROPERTY(mf.name, 'SpaceUsed')) / NULLIF(mf.size, 0) AS DECIMAL(5, 2)) AS FreeSpacePct,
        CAST(vs.total_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(18, 2)) AS DriveSizeGB,
        CAST(vs.available_bytes / 1024.0 / 1024 / 1024 AS DECIMAL(18, 2)) AS DriveFreeSpaceGB,
        CASE
            WHEN vs.available_bytes / 1024.0 / 1024 / 1024 < 5 THEN 'CRITICAL'
            WHEN vs.available_bytes / 1024.0 / 1024 / 1024 < 20 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.master_files mf
    INNER JOIN sys.databases db ON db.database_id = mf.database_id
    CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
    WHERE db.database_id > 4
        AND db.state_desc = 'ONLINE'
        AND (@DatabaseName IS NULL OR db.name = @DatabaseName)
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, DriveFreeSpaceGB ASC
FOR JSON AUTO, INCLUDE_NULL_VALUES
