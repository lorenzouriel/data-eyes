-- Allow advanced options
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;

-- Enable Ad Hoc Distributed Queries
EXEC sp_configure 'Ad Hoc Distributed Queries', 1;
RECONFIGURE

SELECT 
	*
FROM [fact].[earth] AS local
JOIN OPENDATASOURCE(
    'SQLNCLI',
    'Server=server.lorenzo,14330;Uid=;Pwd=;'
).[turritopsis].[fact].[earth] AS remote
    ON local.id = remote.id;