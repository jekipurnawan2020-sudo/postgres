SELECT source_schema, source_table, capture_instance, start_lsn, supports_net_changes
FROM cdc.change_tables
ORDER BY source_schema, source_table;