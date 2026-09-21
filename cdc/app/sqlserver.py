from collections.abc import Iterator
from typing import Any

import pyodbc

from config import Settings


class SqlServer:
	def __init__(self, settings: Settings) -> None:
		self.settings = settings
		self.connection: pyodbc.Connection | None = None

	def connect(self) -> pyodbc.Connection:
		if self.connection is None:
			connection_string = (
				"DRIVER={ODBC Driver 18 for SQL Server};"
				f"SERVER={self.settings.sqlserver_host},{self.settings.sqlserver_port};"
				f"DATABASE={self.settings.sqlserver_database};"
				f"UID={self.settings.sqlserver_user};PWD={self.settings.sqlserver_password};"
				f"Encrypt={self.settings.sqlserver_encrypt};"
				f"TrustServerCertificate={self.settings.sqlserver_trust_server_certificate};"
			)
			self.connection = pyodbc.connect(connection_string, autocommit=True)
		return self.connection

	def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
		cursor = self.connect().cursor()
		cursor.execute(sql, parameters)
		columns = [column[0] for column in cursor.description or ()]
		return [dict(zip(columns, row)) for row in cursor.fetchall()]

	def stream(self, sql: str, parameters: tuple[Any, ...] = ()) -> Iterator[dict[str, Any]]:
		cursor = self.connect().cursor()
		cursor.execute(sql, parameters)
		columns = [column[0] for column in cursor.description or ()]
		for row in cursor:
			yield dict(zip(columns, row))

	def close(self) -> None:
		if self.connection is not None:
			self.connection.close()
			self.connection = None
