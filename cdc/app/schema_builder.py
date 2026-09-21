from typing import Any


def normalize_value(value: Any) -> Any:
	return value.hex() if isinstance(value, bytes) else value


def build_event(row: dict[str, Any]) -> dict[str, Any]:
	return {key: normalize_value(value) for key, value in row.items() if not key.startswith("__$")}


def record_key(row: dict[str, Any], primary_keys: tuple[str, ...]) -> dict[str, Any]:
	return {key: normalize_value(row[key]) for key in primary_keys if key in row}
