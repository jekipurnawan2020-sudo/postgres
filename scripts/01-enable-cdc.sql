USE [SolarWindsOrion];
GO
EXEC sys.sp_cdc_enable_db;
GO

DECLARE @schema sysname;
DECLARE @table sysname;
DECLARE table_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT s.name, t.name
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0
  AND EXISTS (
	  SELECT 1
	  FROM sys.indexes AS i
	  WHERE i.object_id = t.object_id AND i.is_primary_key = 1
  )
  AND NOT EXISTS (
	  SELECT 1 FROM cdc.change_tables AS c
	  WHERE c.source_object_id = t.object_id
  );

OPEN table_cursor;
FETCH NEXT FROM table_cursor INTO @schema, @table;
WHILE @@FETCH_STATUS = 0
BEGIN
	EXEC sys.sp_cdc_enable_table
		@source_schema = @schema,
		@source_name = @table,
		@role_name = NULL,
		@supports_net_changes = 1;
	FETCH NEXT FROM table_cursor INTO @schema, @table;
END;
CLOSE table_cursor;
DEALLOCATE table_cursor;