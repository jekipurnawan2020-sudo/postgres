USE [MyDatabase];
GO
EXEC sys.sp_cdc_enable_db;
GO

-- Enable a table explicitly after replacing schema and table names.
-- EXEC sys.sp_cdc_enable_table @source_schema = N'dbo', @source_name = N'YourTable',
--     @role_name = NULL, @supports_net_changes = 1;