from dataclasses import dataclass

from sqlserver import SqlServer


@dataclass(frozen=True)
class CaptureTable:
    schema: str
    table: str
    capture_instance: str


class Metadata:
    def __init__(self, sqlserver: SqlServer) -> None:
        self.sqlserver = sqlserver

    def capture_tables(self) -> list[CaptureTable]:
        rows = self.sqlserver.query(
            """
            SELECT source_schema, source_table, capture_instance
            FROM cdc.change_tables
            WHERE supports_net_changes = 1 OR supports_net_changes = 0
            ORDER BY source_schema, source_table
            """
        )
        return [CaptureTable(row["source_schema"], row["source_table"], row["capture_instance"]) for row in rows]
