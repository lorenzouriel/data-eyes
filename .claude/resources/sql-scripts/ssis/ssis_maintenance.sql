SELECT 
	[name], 
	[recovery_model_desc]
FROM sys.databases
WHERE name = 'SSISDB';

-- Clean execution logs 
EXEC [SSISDB].[internal].[cleanup_server_retention_window]

-- TABLES THAT WILL BE CLEANED UP
--[internal].[event_message_context_scaleout]
--[internal].[event_messages_scaleout]
--[internal].[executable_statistics]
--[internal].[execution_component_phases]
--[internal].[execution_data_statistics]
--[internal].[execution_data_taps]
--[internal].[execution_parameter_values]
--[internal].[execution_parameter_values_noncatalog]
--[internal].[execution_property_override_values]
--[internal].[execution_property_override_values_noncatalog]
--[internal].[executions]
--[internal].[executions_noncatalog]
--[internal].[extended_operation_info]
--[internal].[operation_messages]
--[internal].[operation_messages_scaleout]
--[internal].[operation_permissions]
--[internal].[operations]
--[internal].[validations]

-- Clean completed logs 
EXEC [SSISDB].[internal].[cleanup_completed_jobs_exclusive]

-- TABLES THAT WILL BE CLEANED UP
--[internal].[job_worker_agents]
--[internal].[jobs]
--[internal].[tasks]


-- Check Total Space
USE SSISDB;
GO
EXEC sp_spaceused;
GO

-- Backup the FULL log
BACKUP DATABASE SSISDB
TO DISK = 'C:\Backup\backup_full.trn';

-- Backup the LOG
BACKUP LOG SSISDB
TO DISK = 'C:\Backup\backup_log.trn';

-- Recover physical disk
USE SSISDB;
GO
DBCC SHRINKDATABASE (SSISDB, 10);