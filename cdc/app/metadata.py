from dataclasses import dataclass

from sqlserver import SqlServer


@dataclass(frozen=True)
class CaptureTable:
    schema: str
    table: str
    capture_instance: str
    primary_keys: tuple[str, ...]


class Metadata:
    def __init__(self, sqlserver: SqlServer) -> None:
        self.sqlserver = sqlserver

    def capture_tables(self) -> list[CaptureTable]:
        rows = self.sqlserver.query(
            """
            SELECT ct.source_schema, ct.source_table, ct.capture_instance,
                   c.name AS column_name, ic.key_ordinal
            FROM cdc.change_tables AS ct
            LEFT JOIN sys.tables AS t ON t.object_id = ct.source_object_id
            LEFT JOIN sys.indexes AS i ON i.object_id = t.object_id AND i.is_primary_key = 1
            LEFT JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
            LEFT JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
            ORDER BY ct.source_schema, ct.source_table, ic.key_ordinal
            """
        )
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            key = row["capture_instance"]
            item = grouped.setdefault(key, {
                "schema": row["source_schema"],
                "table": row["source_table"],
                "primary_keys": [],
            })
            if row["column_name"]:
                item["primary_keys"].append(row["column_name"])
        return [CaptureTable(item["schema"], item["table"], key, tuple(item["primary_keys"]))
                for key, item in grouped.items()]
