-- Author: Lorenzo Uriel
-- Created: 2025-10-31

EXEC sp_updateextendedproperty
    @name = N'MS_Description',
    @value = N'Table containing user accounts and credentials',
    @level0type = N'Schema', @level0name = 'dbo',
    @level1type = N'Table',  @level1name = 'users';

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'Primary key – unique user identifier',
    @level0type = N'Schema', @level0name = 'dbo',
    @level1type = N'Table',  @level1name = 'users',
    @level2type = N'Column', @level2name = 'id';

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'Email address of the user',
    @level0type = N'Schema', @level0name = 'dbo',
    @level1type = N'Table',  @level1name = 'users',
    @level2type = N'Column', @level2name = 'email';


SELECT 
    obj.name AS [Table],
    col.name AS [Column],
    ep.value AS [Description]
FROM sys.extended_properties AS ep
INNER JOIN sys.objects AS obj ON ep.major_id = obj.object_id
LEFT JOIN sys.columns AS col ON ep.major_id = col.object_id AND ep.minor_id = col.column_id
WHERE obj.name = 'users';
