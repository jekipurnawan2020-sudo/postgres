SELECT
    OBJECT_SCHEMA_NAME(source_object_id) AS source_schema,
    OBJECT_NAME(source_object_id) AS source_table,
    capture_instance,
    start_lsn,
    supports_net_changes
FROM cdc.change_tables
ORDER BY OBJECT_SCHEMA_NAME(source_object_id), OBJECT_NAME(source_object_id);