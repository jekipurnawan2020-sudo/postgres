from dataclasses import dataclass
import os


def _env(name: str, default: str | None = None) -> str:
	value = os.getenv(name, default)
	if value is None or value == "":
		raise ValueError(f"Missing required environment variable: {name}")
	return value


@dataclass(frozen=True)
class Settings:
	sqlserver_host: str
	sqlserver_port: int
	sqlserver_database: str
	sqlserver_user: str
	sqlserver_password: str
	sqlserver_encrypt: str
	sqlserver_trust_server_certificate: str
	postgres_host: str
	postgres_port: int
	postgres_db: str
	postgres_user: str
	postgres_password: str
	kafka_bootstrap_servers: str
	kafka_topic_prefix: str
	cdc_batch_size: int
	cdc_poll_interval: float
	checkpoint_table: str
	target_schema: str
	connect_rest_url: str
	initial_load_enabled: bool
	register_connectors: bool
	connector_tasks_max: int
	connector_auto_create: bool
	connector_auto_evolve: bool


def load_settings() -> Settings:
	return Settings(
		sqlserver_host=_env("SQLSERVER_HOST"),
		sqlserver_port=int(_env("SQLSERVER_PORT", "1433")),
		sqlserver_database=_env("SQLSERVER_DATABASE"),
		sqlserver_user=_env("SQLSERVER_USER"),
		sqlserver_password=_env("SQLSERVER_PASSWORD"),
		sqlserver_encrypt=_env("SQLSERVER_ENCRYPT", "no"),
		sqlserver_trust_server_certificate=_env("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes"),
		postgres_host=_env("POSTGRES_HOST"),
		postgres_port=int(_env("POSTGRES_PORT", "5432")),
		postgres_db=_env("POSTGRES_DB", "migratedb"),
		postgres_user=_env("POSTGRES_USER"),
		postgres_password=_env("POSTGRES_PASSWORD"),
		kafka_bootstrap_servers=_env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
		kafka_topic_prefix=_env("KAFKA_TOPIC_PREFIX", "solarwonds"),
		cdc_batch_size=int(_env("CDC_BATCH_SIZE", "1000")),
		cdc_poll_interval=float(_env("CDC_POLL_INTERVAL", "1")),
		checkpoint_table=_env("CHECKPOINT_TABLE", "migration_control.cdc_checkpoint"),
		target_schema=_env("TARGET_SCHEMA", "solarwinds"),
		connect_rest_url=_env("CONNECT_REST_URL", "http://kafka-connect:8083"),
		initial_load_enabled=_env("INITIAL_LOAD_ENABLED", "false").lower() == "true",
		register_connectors=_env("REGISTER_CONNECTORS", "true").lower() == "true",
		connector_tasks_max=int(_env("CONNECTOR_TASKS_MAX", "1")),
		connector_auto_create=_env("CONNECTOR_AUTO_CREATE", "true").lower() == "true",
		connector_auto_evolve=_env("CONNECTOR_AUTO_EVOLVE", "true").lower() == "true",
	)
