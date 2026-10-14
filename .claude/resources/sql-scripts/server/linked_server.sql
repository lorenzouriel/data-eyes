EXEC sp_addlinkedserver 
    @server     = N'server.lorenzo.com.br,14330',  
    @srvproduct = N'SQL Server';

EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = N'server.lorenzo.com.br,14330',
    @useself    = 'false',
    @locallogin = NULL,
    @rmtuser    = '',
    @rmtpassword= '';