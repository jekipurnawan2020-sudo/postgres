import logging

import psycopg

from config import Settings
from metadata import CaptureTable
from pg_types import map_type, quote_ident
from sqlserver import SqlServer

logger = logging.getLogger(__name__)

COLUMNS_SQL = """
	SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
	       NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
	FROM INFORMATION_SCHEMA.COLUMNS
	WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
	ORDER BY ORDINAL_POSITION
"""


class SchemaSync:
	"""Buat/sinkronkan struktur tabel target di PostgreSQL sebelum Kafka Connect
	mulai menulis data, supaya tipe kolom (numeric, timestamp, uuid, dst) benar
	sejak awal alih-alih ditebak dari JSON tanpa schema oleh JDBC Sink.

	Read-only terhadap SQL Server: hanya SELECT ke INFORMATION_SCHEMA.COLUMNS,
	tidak pernah INSERT/UPDATE/DELETE/ALTER apa pun di sisi source.
	Terhadap PostgreSQL hanya CREATE SCHEMA/TABLE IF NOT EXISTS (idempotent,
	tidak pernah DROP atau ALTER kolom yang sudah ada).
	"""

	def __init__(self, settings: Settings, sqlserver: SqlServer) -> None:
		self.settings = settings
		self.sqlserver = sqlserver

	def _connect_postgres(self) -> psycopg.Connection:
		return psycopg.connect(
			host=self.settings.postgres_host,
			port=self.settings.postgres_port,
			dbname=self.settings.postgres_db,
			user=self.settings.postgres_user,
			password=self.settings.postgres_password,
		)

	def _table_ddl(self, table: CaptureTable) -> str:
		columns = self.sqlserver.query(COLUMNS_SQL, (table.schema, table.table))
		target_table = table.table.lower()
		column_defs: list[str] = []
		for row in columns:
			pg_type, needs_review = map_type(
				row["DATA_TYPE"], row["CHARACTER_MAXIMUM_LENGTH"], row["NUMERIC_PRECISION"], row["NUMERIC_SCALE"]
			)
			if needs_review:
				logger.warning(
					"%s.%s: source type '%s' has no exact PostgreSQL mapping, using text",
					table.table, row["COLUMN_NAME"], row["DATA_TYPE"],
				)
			nullable = "" if row["IS_NULLABLE"] == "YES" else " NOT NULL"
			column_defs.append(f"{quote_ident(row['COLUMN_NAME'])} {pg_type}{nullable}")
		if table.primary_keys:
			pk_list = ", ".join(quote_ident(c) for c in table.primary_keys)
			column_defs.append(f"PRIMARY KEY ({pk_list})")
		columns_sql = ",\n    ".join(column_defs)
		target_schema = quote_ident(self.settings.target_schema)
		return f"CREATE TABLE IF NOT EXISTS {target_schema}.{quote_ident(target_table)} (\n    {columns_sql}\n)"

	def apply(self, tables: list[CaptureTable]) -> None:
		if not tables:
			return
		connection = self._connect_postgres()
		try:
			with connection.cursor() as cursor:
				cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(self.settings.target_schema)}")
				for table in tables:
					cursor.execute(self._table_ddl(table))
			connection.commit()
			logger.info("Schema sync applied for %d table(s) in schema '%s'", len(tables), self.settings.target_schema)
		finally:
			connection.close()
