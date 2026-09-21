from typing import Any


def normalize_value(value: Any) -> Any:
	return value.hex() if isinstance(value, bytes) else value


def build_event(row: dict[str, Any], operation: str, source_table: str) -> dict[str, Any]:
	return {
		"operation": operation,
		"source_table": source_table,
		"data": {key: normalize_value(value) for key, value in row.items() if not key.startswith("__$")},
	}
