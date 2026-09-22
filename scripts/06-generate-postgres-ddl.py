"""Generate PostgreSQL target DDL from SolarWinds SQL Server table metadata.

Kenapa script ini ada
----------------------
Kafka Connect JDBC Sink pada stack ini dikonfigurasi dengan
`key.converter.schemas.enable=false` dan `value.converter.schemas.enable=false`
(lihat cdc/app/connector_registry.py). Artinya setiap pesan Kafka adalah JSON
tanpa schema, dan saat `auto.create=true`, JDBC Sink menebak tipe kolom
PostgreSQL dari tipe JSON masing-masing value. Karena reader Python
(cdc/app/producer.py) melakukan `json.dumps(payload, default=str)`, nilai
`Decimal` (money, numeric SolarWinds) dan `datetime` (kolom polling/timestamp)
ikut berubah jadi JSON string. Hasilnya JDBC Sink akan membuat kolom itu
sebagai TEXT/VARCHAR di PostgreSQL, bukan NUMERIC/TIMESTAMP -- data tetap
masuk tapi query/agregasi di sisi PostgreSQL jadi salah atau butuh CAST
manual di setiap query.

Script ini membaca metadata kolom & primary key langsung dari SQL Server
(INFORMATION_SCHEMA + cdc.change_tables) dan membuat `CREATE TABLE` PostgreSQL
dengan tipe data yang benar, supaya tabel target sudah punya struktur final
SEBELUM Kafka Connect mengisi datanya.

PENTING: sejak cdc/app/schema_sync.py ditambahkan, langkah ini sudah berjalan
OTOMATIS setiap kali container `cdc` start (lihat cdc/app/main.py) -- tidak
perlu dijalankan manual untuk deployment normal. Script ini sekarang berguna
untuk:
  - Preview DDL SEBELUM deployment pertama, tanpa menyalakan stack dulu.
  - Review manual saat ada tabel dengan tipe data yang perlu penyesuaian
    (kolom "-- WARNING" di bawah).
  - Debug lewat host, tanpa masuk ke dalam container.

Cara pakai (step by step)
--------------------------
1. Pastikan CDC sudah diaktifkan di SQL Server (scripts/01-enable-cdc.sql)
   sehingga cdc.change_tables terisi -- script ini hanya memproses tabel yang
   sudah CDC-enabled (scope yang sama dengan yang dibaca cdc/app/metadata.py).
2. Install dependency di host yang punya akses ODBC ke SQL Server:
       pip install pyodbc psycopg[binary] python-dotenv
3. Jalankan dalam mode "dry run" dulu (tidak menyentuh PostgreSQL sama sekali,
   hanya menulis file .sql untuk direview):
       python scripts/06-generate-postgres-ddl.py
   File akan tertulis ke scripts/generated/postgres-ddl-<timestamp>.sql
4. Baca file yang dihasilkan. Perhatikan baris yang diawali komentar
   "-- WARNING" -- itu adalah kolom dengan tipe SQL Server yang tidak punya
   pemetaan pasti (mis. sql_variant, geography/geometry, hierarchyid) dan
   sementara dipetakan ke TEXT. Sesuaikan manual bila perlu.
5. (Opsional) Terapkan lebih awal ke PostgreSQL sebelum stack pertama kali
   naik -- kalau tidak dijalankan pun, cdc/app/schema_sync.py akan tetap
   membuatnya otomatis saat container start:
       psql -h <POSTGRES_HOST> -U <POSTGRES_USER> -d <POSTGRES_DB> \
            -f scripts/generated/postgres-ddl-<timestamp>.sql
   atau langsung dari script ini dengan flag --apply:
       python scripts/06-generate-postgres-ddl.py --apply
6. `docker-compose up -d --build` seperti biasa.

Catatan penting soal huruf besar/kecil (case sensitivity)
-----------------------------------------------------------
connector_registry.py men-generate `table.name.format` dari
`table.table.lower()` (nama tabel selalu lowercase), tapi TIDAK melakukan
lowercase pada nama kolom -- nama kolom JSON persis sama dengan nama kolom
SQL Server aslinya (mis. "NodeID", "IPAddress"), dan connector dikonfigurasi
`quote.identifiers=true`. Karena itu script ini SENGAJA membuat nama tabel
lowercase tanpa quote, tapi nama kolom quoted dengan huruf besar/kecil asli.
Kalau ini tidak konsisten, JDBC Sink akan menganggap kolom "belum ada" dan
mencoba auto-evolve menambah kolom duplikat dengan nama ter-lowercase.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import pyodbc

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "generated"

# pg_types.py lives in cdc/app/. Two layouts are supported so this script runs
# both from a repo checkout (scripts/ + cdc/app/ as siblings) and inside the
# `cdc` container, where the Dockerfile copies this repo's cdc/app/ to /app/app
# and scripts/ to /app/scripts (siblings under /app instead).
for _candidate in (SCRIPT_DIR.parent / "cdc" / "app", SCRIPT_DIR.parent / "app"):
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise SystemExit("Cannot locate cdc/app (pg_types.py) -- run from the repo root or inside the cdc container.")

from pg_types import map_type, quote_ident  # noqa: E402  (shared with cdc/app/schema_sync.py)

CAPTURE_TABLES_SQL = """
    SELECT DISTINCT ct.source_schema, ct.source_table
    FROM cdc.change_tables AS ct
    ORDER BY ct.source_schema, ct.source_table
"""

COLUMNS_SQL = """
    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, ORDINAL_POSITION
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
    ORDER BY ORDINAL_POSITION
"""

PRIMARY_KEY_SQL = """
    SELECT kcu.COLUMN_NAME
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ?
    ORDER BY kcu.ORDINAL_POSITION
"""


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def sqlserver_connection() -> pyodbc.Connection:
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={env('SQLSERVER_HOST')},{env('SQLSERVER_PORT', '1433')};"
        f"DATABASE={env('SQLSERVER_DATABASE')};"
        f"UID={env('SQLSERVER_USER')};PWD={env('SQLSERVER_PASSWORD')};"
        f"Encrypt={env('SQLSERVER_ENCRYPT', 'no')};"
        f"TrustServerCertificate={env('SQLSERVER_TRUST_SERVER_CERTIFICATE', 'yes')};"
    )
    return pyodbc.connect(connection_string, autocommit=True)


def build_table_ddl(schema: str, table: str, target_schema: str, columns: list, pk_columns: list[str]) -> str:
    target_table = table.lower()
    lines = [f'CREATE TABLE IF NOT EXISTS {quote_ident(target_schema)}.{quote_ident(target_table)} (']
    column_defs = []
    for row in columns:
        pg_type, needs_review = map_type(row.DATA_TYPE, row.CHARACTER_MAXIMUM_LENGTH, row.NUMERIC_PRECISION, row.NUMERIC_SCALE)
        nullable = "" if row.IS_NULLABLE == "YES" else " NOT NULL"
        warning = f"  -- WARNING: source type '{row.DATA_TYPE}' mapped to TEXT, review manually" if needs_review else ""
        column_defs.append(f"    {quote_ident(row.COLUMN_NAME)} {pg_type}{nullable}{warning}")
    if pk_columns:
        pk_list = ", ".join(quote_ident(c) for c in pk_columns)
        column_defs.append(f"    PRIMARY KEY ({pk_list})")
    lines.append(",\n".join(column_defs))
    lines.append(");")
    return "\n".join(lines)


def generate(connection: pyodbc.Connection, target_schema: str) -> tuple[str, int]:
    cursor = connection.cursor()
    capture_tables = cursor.execute(CAPTURE_TABLES_SQL).fetchall()
    if not capture_tables:
        raise SystemExit(
            "Tidak ada tabel di cdc.change_tables. Jalankan scripts/01-enable-cdc.sql "
            "dan pastikan tabel sudah CDC-enabled sebelum generate DDL."
        )

    statements = [f"CREATE SCHEMA IF NOT EXISTS {quote_ident(target_schema)};", ""]
    for source_schema, source_table in capture_tables:
        columns = cursor.execute(COLUMNS_SQL, (source_schema, source_table)).fetchall()
        pk_rows = cursor.execute(PRIMARY_KEY_SQL, (source_schema, source_table)).fetchall()
        pk_columns = [row.COLUMN_NAME for row in pk_rows]
        statements.append(f"-- source: {source_schema}.{source_table}")
        statements.append(build_table_ddl(source_schema, source_table, target_schema, columns, pk_columns))
        statements.append("")
    return "\n".join(statements), len(capture_tables)


def apply_to_postgres(ddl: str) -> None:
    import psycopg

    connection = psycopg.connect(
        host=env("POSTGRES_HOST"),
        port=int(env("POSTGRES_PORT", "5432")),
        dbname=env("POSTGRES_DB"),
        user=env("POSTGRES_USER"),
        password=env("POSTGRES_PASSWORD"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(ddl)
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Eksekusi langsung ke PostgreSQL (bukan cuma tulis file)")
    parser.add_argument("--schema", default=None, help="Override TARGET_SCHEMA dari .env")
    args = parser.parse_args()

    target_schema = args.schema or env("TARGET_SCHEMA", "solarwinds")

    connection = sqlserver_connection()
    try:
        ddl, table_count = generate(connection, target_schema)
    finally:
        connection.close()

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = OUTPUT_DIR / f"postgres-ddl-{timestamp}.sql"
    output_path.write_text(ddl, encoding="utf-8")

    print(f"Generated DDL for {table_count} table(s): {output_path}")
    warning_count = ddl.count("-- WARNING")
    if warning_count:
        print(f"{warning_count} column(s) need manual review (search for '-- WARNING' in the file).")

    if args.apply:
        print(f"Applying DDL to PostgreSQL schema '{target_schema}' ...")
        apply_to_postgres(ddl)
        print("Done. cdc/app/schema_sync.py will keep re-applying this idempotently on every container start.")
    else:
        print("Dry run only. Review the file, then re-run with --apply or psql -f <file>.")
        print("Note: cdc/app/schema_sync.py already does this automatically on every 'docker-compose up'.")


if __name__ == "__main__":
    sys.exit(main())
