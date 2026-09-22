USE [SolarWindsOrion];
GO
EXEC sys.sp_cdc_enable_db;
GO

IF OBJECT_ID('tempdb..#cdc_enable_failures') IS NOT NULL
	DROP TABLE #cdc_enable_failures;
CREATE TABLE #cdc_enable_failures (
	schema_name sysname,
	table_name sysname,
	error_message nvarchar(4000)
);

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
	BEGIN TRY
		EXEC sys.sp_cdc_enable_table
			@source_schema = @schema,
			@source_name = @table,
			@role_name = NULL,
			@supports_net_changes = 0;
	END TRY
	BEGIN CATCH
		INSERT INTO #cdc_enable_failures (schema_name, table_name, error_message)
		VALUES (@schema, @table, ERROR_MESSAGE());
		PRINT 'SKIP ' + @schema + '.' + @table + ': ' + ERROR_MESSAGE();
	END CATCH
	FETCH NEXT FROM table_cursor INTO @schema, @table;
END;
CLOSE table_cursor;
DEALLOCATE table_cursor;

PRINT '';
PRINT '=== Tabel yang GAGAL di-enable CDC (perlu ditinjau manual) ===';
SELECT * FROM #cdc_enable_failures;
DROP TABLE #cdc_enable_failures;