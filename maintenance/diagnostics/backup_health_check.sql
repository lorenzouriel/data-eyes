-- #######################
-- BACKUP HEALTH CHECK — live observation, read-only
-- Purpose: "Is my backup healthy right now" — the query maintenance/ never had.
--          Reports last FULL/DIFF/LOG backup per database and flags staleness.
-- Thresholds: .claude/knowledge-base/_static/thresholds.yaml -> maintenance.backup
-- Params: @DatabaseName = NULL checks all user databases; set it to check one.
-- #######################

DECLARE @DatabaseName NVARCHAR(128) = NULL;

;WITH LastBackups AS (
    SELECT
        database_name,
        MAX(CASE WHEN [type] = 'D' THEN backup_finish_date END) AS LastFullBackup,
        MAX(CASE WHEN [type] = 'I' THEN backup_finish_date END) AS LastDiffBackup,
        MAX(CASE WHEN [type] = 'L' THEN backup_finish_date END) AS LastLogBackup
    FROM msdb.dbo.backupset
    GROUP BY database_name
),
Base AS (
    SELECT
        d.name AS DatabaseName,
        d.recovery_model_desc AS RecoveryModel,
        lb.LastFullBackup,
        DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) AS FullBackupAgeHours,
        lb.LastDiffBackup,
        lb.LastLogBackup,
        CASE WHEN d.recovery_model_desc <> 'SIMPLE'
             THEN DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE())
             ELSE NULL END AS LogBackupAgeMinutes,
        CASE
            WHEN lb.LastFullBackup IS NULL THEN 'CRITICAL'
            WHEN DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) >= 48 THEN 'CRITICAL'
            WHEN DATEDIFF(HOUR, lb.LastFullBackup, GETDATE()) >= 24 THEN 'WARNING'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND lb.LastLogBackup IS NULL THEN 'CRITICAL'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) >= 240 THEN 'CRITICAL'
            WHEN d.recovery_model_desc <> 'SIMPLE' AND DATEDIFF(MINUTE, lb.LastLogBackup, GETDATE()) >= 60 THEN 'WARNING'
            ELSE 'OK'
        END AS severity
    FROM sys.databases d
    LEFT JOIN LastBackups lb ON lb.database_name = d.name
    WHERE d.database_id > 4                    -- exclude master/tempdb/model/msdb
        AND d.state_desc = 'ONLINE'
        AND (@DatabaseName IS NULL OR d.name = @DatabaseName)
)
SELECT *
FROM Base
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, FullBackupAgeHours DESC
FOR JSON AUTO, INCLUDE_NULL_VALUES
