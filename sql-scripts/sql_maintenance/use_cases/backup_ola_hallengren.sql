-- #######################
-- BACKUP USING OLA HALLENGREN SOLUTION
-- #######################

-- A. Back up all user databases, using checksums and compression; verify the backup; and delete old backup files
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@Verify = 'Y',
	@Compress = 'Y',
	@Checksum = 'Y',
	@CleanupTime = 24

-- B. Back up all user databases to a network share, and verify the backup
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = '\\Server1\Backup',
	@BackupType = 'FULL',
	@Verify = 'Y'

-- C. Back up all user databases across four network shares, and verify the backup
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = '\\Server1\Backup, \\Server2\Backup, \\Server3\Backup, \\Server4\Backup',
	@BackupType = 'FULL',
	@Verify = 'Y',
	@NumberOfFiles = 4

-- D. Back up all user databases to 64 files, using checksums and compression and setting the buffer count and the maximum transfer size
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@Compress = 'Y',
	@Checksum = 'Y',
	@BufferCount = 50,
	@MaxTransferSize = 4194304,
	@NumberOfFiles = 64

-- E. Back up all user databases to Azure Blob Storage, using compression
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@URL = 'https://myaccount.blob.core.windows.net/mycontainer',
	@Credential = 'MyCredential',
	@BackupType = 'FULL',
	@Compress = 'Y',
	@Verify = 'Y'

-- F. Back up all user databases to S3 storage, using compression
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@URL = 's3://myaccount.s3.us-east-1.amazonaws.com/mybucket',
	@BackupType = 'FULL',
	@Compress = 'Y',
	@Verify = 'Y',
	@MaxTransferSize = 20971520,
	@BackupOptions = '{"s3": {"region":"us-east-1"}}'

-- G. Back up the transaction log of all user databases, using the option to change the backup type if a log backup cannot be performed
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'LOG',
	@ChangeBackupType = 'Y'

-- H. Back up all user databases, using compression, encryption, and a server certificate.
EXECUTE dbo.DatabaseBackup @Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@Compress = 'Y',
	@Encrypt = 'Y',
	@EncryptionAlgorithm = 'AES_256',
	@ServerCertificate = 'MyCertificate'

-- I. Back up all user databases, using compression, encryption, and LiteSpeed, and limiting the CPU usage to 10 percent
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@BackupSoftware = 'LITESPEED',
	@Compress = 'Y',
	@Encrypt = 'Y',
	@EncryptionAlgorithm = 'AES_256',
	@EncryptionKey = 'MyPassword',
	@Throttle = 10

-- J. Back up all user databases, using compression, encryption, and Red Gate SQL Backup Pro
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@BackupSoftware = 'SQLBACKUP',
	@Compress = 'Y',
	@Encrypt = 'Y',
	@EncryptionAlgorithm = 'AES_256',
	@EncryptionKey = 'MyPassword'

-- K. Back up all user databases, using compression, encryption, and Idera SQL Safe Backup
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@BackupSoftware = 'SQLSAFE',
	@Compress = 'Y',
	@Encrypt = 'Y',
	@EncryptionAlgorithm = 'AES_256',
	@EncryptionKey = '8tPyzp4i1uF/ydAN1DqevdXDeVoryWRL'

-- L. Back up all user databases, using mirrored backups.
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@MirrorDirectory = 'D:\Backup',
	@BackupType = 'FULL',
	@Compress = 'Y',
	@Verify = 'Y',
	@CleanupTime = 24,
	@MirrorCleanupTime = 48

-- M. Back up all user databases, using Data Domain Boost.
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@BackupType = 'FULL',
	@Checksum = 'Y',
	@BackupSoftware = 'DATA_DOMAIN_BOOST',
	@DataDomainBoostHost = 'Host',
	@DataDomainBoostUser = 'User',
	@DataDomainBoostDevicePath = '/DevicePath',
	@DataDomainBoostLockboxPath = 'C:\Program Files\DPSAPPS\common\lockbox',
	@CleanupTime = 24

-- N. Back up all user databases, with the default directory structure and file names.
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@DirectoryStructure = '{ServerName}${InstanceName}{DirectorySeparator}{DatabaseName}{DirectorySeparator}{BackupType}_{Partial}_{CopyOnly}',
	@AvailabilityGroupDirectoryStructure = '{ClusterName}${AvailabilityGroupName}{DirectorySeparator}{DatabaseName}{DirectorySeparator}{BackupType}_{Partial}_{CopyOnly}',
	@FileName = '{ServerName}${InstanceName}_{DatabaseName}_{BackupType}_{Partial}_{CopyOnly}_{Year}{Month}{Day}_{Hour}{Minute}{Second}_{FileNumber}.{FileExtension}',
	@AvailabilityGroupFileName = '{ClusterName}${AvailabilityGroupName}_{DatabaseName}_{BackupType}_{Partial}_{CopyOnly}_{Year}{Month}{Day}_{Hour}{Minute}{Second}_{FileNumber}.{FileExtension}'

-- O. Back up all user databases, to a directory structure without the server name, instance name, cluster name, and availability group name.
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@DirectoryStructure = '{DatabaseName}{DirectorySeparator}{BackupType}_{Partial}_{CopyOnly}',
	@AvailabilityGroupDirectoryStructure = '{DatabaseName}{DirectorySeparator}{BackupType}_{Partial}_{CopyOnly}'

-- P. Back up all user databases, without creating any sub-directories.
EXECUTE dbo.DatabaseBackup
	@Databases = 'USER_DATABASES',
	@Directory = 'C:\Backup',
	@BackupType = 'FULL',
	@DirectoryStructure = NULL,
	@AvailabilityGroupDirectoryStructure = NULL