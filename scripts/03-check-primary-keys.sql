SELECT sch.name AS schema_name, tab.name AS table_name, col.name AS column_name
FROM sys.tables tab
JOIN sys.schemas sch ON sch.schema_id = tab.schema_id
JOIN sys.indexes ind ON ind.object_id = tab.object_id AND ind.is_primary_key = 1
JOIN sys.index_columns ic ON ic.object_id = ind.object_id AND ic.index_id = ind.index_id
JOIN sys.columns col ON col.object_id = ic.object_id AND col.column_id = ic.column_id
ORDER BY sch.name, tab.name, ic.key_ordinal;