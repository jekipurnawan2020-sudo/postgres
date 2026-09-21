from typing import Any

from sqlserver import SqlServer


class InitialLoader:
	def __init__(self, sqlserver: SqlServer, batch_size: int) -> None:
		self.sqlserver = sqlserver
		self.batch_size = batch_size

	def load(self, schema: str, table: str) -> list[dict[str, Any]]:
		return self.sqlserver.query(f'SELECT TOP (?) * FROM [{schema}].[{table}]', (self.batch_size,))
