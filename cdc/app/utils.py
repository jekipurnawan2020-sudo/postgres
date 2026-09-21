from typing import Any


def lsn_to_text(value: Any) -> str:
	if isinstance(value, bytes):
		return value.hex().upper()
	return str(value)


def operation_name(operation: Any) -> str:
	return {1: "delete", 2: "insert", 3: "update_before", 4: "update_after"}.get(operation, "unknown")
