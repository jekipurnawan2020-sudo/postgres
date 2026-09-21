CREATE SCHEMA IF NOT EXISTS migration_control;

CREATE TABLE IF NOT EXISTS migration_control.cdc_checkpoint (
    capture_instance text PRIMARY KEY,
    start_lsn text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);