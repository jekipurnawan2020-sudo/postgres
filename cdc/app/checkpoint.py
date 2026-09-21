import psycopg

from config import Settings


class CheckpointStore:
	def __init__(self, settings: Settings) -> None:
		self.settings = settings
		self.connection: psycopg.Connection | None = None

	def connect(self) -> psycopg.Connection:
		if self.connection is None:
			self.connection = psycopg.connect(
				host=self.settings.postgres_host,
				port=self.settings.postgres_port,
				dbname=self.settings.postgres_db,
				user=self.settings.postgres_user,
				password=self.settings.postgres_password,
			)
		return self.connection

	def ensure_table(self) -> None:
		schema, table = self.settings.checkpoint_table.split(".", 1)
		with self.connect().cursor() as cursor:
			cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.settings.target_schema}"')
			cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
			cursor.execute(f'''CREATE TABLE IF NOT EXISTS "{schema}"."{table}" (
				capture_instance text PRIMARY KEY,
				start_lsn text NOT NULL,
				updated_at timestamptz NOT NULL DEFAULT now()
			)''')
		self.connect().commit()

	def get(self, capture_instance: str) -> str | None:
		schema, table = self.settings.checkpoint_table.split(".", 1)
		with self.connect().cursor() as cursor:
			cursor.execute(f'SELECT start_lsn FROM "{schema}"."{table}" WHERE capture_instance = %s', (capture_instance,))
			row = cursor.fetchone()
		return row[0] if row else None

	def save(self, capture_instance: str, start_lsn: str) -> None:
		schema, table = self.settings.checkpoint_table.split(".", 1)
		with self.connect().cursor() as cursor:
			cursor.execute(f'''INSERT INTO "{schema}"."{table}" (capture_instance, start_lsn)
				VALUES (%s, %s) ON CONFLICT (capture_instance) DO UPDATE SET
				start_lsn = EXCLUDED.start_lsn, updated_at = now()''', (capture_instance, start_lsn))
		self.connect().commit()

	def close(self) -> None:
		if self.connection is not None:
			self.connection.close()
			self.connection = None
