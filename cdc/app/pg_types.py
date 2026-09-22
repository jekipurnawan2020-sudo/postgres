SIMPLE_TYPE_MAP = {
	"bigint": "bigint",
	"int": "integer",
	"smallint": "smallint",
	"tinyint": "smallint",
	"bit": "boolean",
	"money": "numeric(19,4)",
	"smallmoney": "numeric(10,4)",
	"float": "double precision",
	"real": "real",
	"date": "date",
	"datetime": "timestamp",
	"datetime2": "timestamp",
	"smalldatetime": "timestamp",
	"datetimeoffset": "timestamptz",
	"time": "time",
	"text": "text",
	"ntext": "text",
	"uniqueidentifier": "uuid",
	"xml": "xml",
	"rowversion": "bytea",
	"timestamp": "bytea",
	"sql_variant": "text",
	"geography": "text",
	"geometry": "text",
	"hierarchyid": "text",
}

NEEDS_MANUAL_REVIEW = {"sql_variant", "geography", "geometry", "hierarchyid"}


def map_type(data_type: str, char_len: int | None, precision: int | None, scale: int | None) -> tuple[str, bool]:
	data_type = data_type.lower()
	if data_type in ("decimal", "numeric"):
		return f"numeric({precision or 18},{scale or 0})", False
	if data_type in ("char", "varchar", "nchar", "nvarchar"):
		if char_len is None or char_len == -1:
			return "text", False
		return f"varchar({char_len})", False
	if data_type in ("binary", "varbinary", "image"):
		return "bytea", False
	if data_type in SIMPLE_TYPE_MAP:
		return SIMPLE_TYPE_MAP[data_type], data_type in NEEDS_MANUAL_REVIEW
	return "text", True


def quote_ident(name: str) -> str:
	return '"' + name.replace('"', '""') + '"'
