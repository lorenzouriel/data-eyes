-- =============================================
-- PURPOSE: Retrieve detailed information about foreign key constraints
-- including parent and referenced tables and columns, 
-- as well as update and delete rules.
-- 
-- NOTES:
-- - Uses sys.foreign_keys for FK definitions
-- - Uses sys.foreign_key_columns to join columns correctly
-- - Uses sys.tables and sys.columns for table/column names
-- - Filtered for a specific parent table (replace 'YourTableName')
-- =============================================

SELECT 
    fk.name AS Nome_Constraint,                         -- Name of the foreign key constraint
    tp.name AS Tabela_Pai,                              -- Parent table (table with the foreign key)
    rf.name AS Coluna_Pai,                              -- Column in the parent table
    tr.name AS Tabela_Filha,                            -- Referenced table (child table)
    ff.name AS Coluna_Filha,                            -- Column in the referenced table
    fk.update_referential_action_desc AS Regra_Atualizacao, -- Action on update (CASCADE, NO ACTION, etc.)
    fk.delete_referential_action_desc AS Regra_Exclusao     -- Action on delete (CASCADE, NO ACTION, etc.)
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc
    ON fk.object_id = fkc.constraint_object_id         -- Join to get the FK column mapping
INNER JOIN sys.tables AS tp
    ON fkc.parent_object_id = tp.object_id            -- Join to get parent table name
INNER JOIN sys.columns AS rf
    ON fkc.parent_object_id = rf.object_id            -- Join to get parent column name
    AND fkc.parent_column_id = rf.column_id
INNER JOIN sys.tables AS tr
    ON fkc.referenced_object_id = tr.object_id        -- Join to get referenced table name
INNER JOIN sys.columns AS ff
    ON fkc.referenced_object_id = ff.object_id        -- Join to get referenced column name
    AND fkc.referenced_column_id = ff.column_id
WHERE tp.name = 'YourTableName';                        -- Filter by parent table (replace with actual table name)