# Konversi Skema: SQL Server (SolarWinds) → PostgreSQL

Dokumen ini menjelaskan bagaimana struktur tabel target di PostgreSQL dibuat, kenapa itu perlu dilakukan secara eksplisit (bukan dibiarkan ditebak otomatis oleh Kafka Connect), dan jaminan keamanannya terhadap SQL Server sumber (SolarWinds).

## 1. Masalah yang diselesaikan

Kafka Connect JDBC Sink pada stack ini dikonfigurasi schemaless:

```
key.converter.schemas.enable=false
value.converter.schemas.enable=false
```

(lihat [cdc/app/connector_registry.py](../cdc/app/connector_registry.py))

Setiap pesan Kafka adalah JSON polos tanpa metadata tipe. Kalau `auto.create=true` dibiarkan menebak sendiri, JDBC Sink menyimpulkan tipe kolom PostgreSQL dari tipe nilai JSON per pesan. Karena [cdc/app/producer.py](../cdc/app/producer.py) melakukan `json.dumps(payload, default=str)`, nilai Python `Decimal` (kolom `money`/`numeric` SolarWinds, mis. biaya lisensi, threshold) dan `datetime` (kolom polling/timestamp, mis. `LastSync`, `DateTime`) ikut berubah jadi string sebelum sampai ke Kafka. Akibatnya JDBC Sink membuat kolom itu sebagai `TEXT`/`VARCHAR`, bukan `NUMERIC`/`TIMESTAMP` — data tetap masuk, tapi query agregasi, `ORDER BY` waktu, atau join berbasis tanggal di PostgreSQL jadi salah atau butuh `CAST` manual di setiap query turunan.

## 2. Solusi: schema dibuat lebih dulu, dengan tipe yang benar

Ada dua komponen yang saling melengkapi, keduanya memakai tabel pemetaan tipe yang sama di [cdc/app/pg_types.py](../cdc/app/pg_types.py):

| Komponen | Kapan jalan | Tujuan |
|---|---|---|
| [cdc/app/schema_sync.py](../cdc/app/schema_sync.py) | **Otomatis**, setiap kali container `cdc` start, sebelum connector JDBC Sink didaftarkan ([main.py](../cdc/app/main.py)) | Memastikan tabel target selalu ada dengan tipe benar sebelum data pertama ditulis. Tidak perlu langkah manual untuk deployment normal. |
| [scripts/06-generate-postgres-ddl.py](../scripts/06-generate-postgres-ddl.py) | **Manual**, dijalankan dari host kapan pun Anda mau | Preview DDL sebelum stack pertama kali dijalankan, atau untuk audit/debug tanpa masuk ke container. |

Urutan startup di `cdc/app/main.py`:

```
Metadata.capture_tables()      # baca daftar tabel CDC-enabled dari cdc.change_tables
TopicManager.ensure()          # buat topic Kafka
SchemaSync.apply()             # buat schema + tabel PostgreSQL dengan tipe benar   <-- BARU
ConnectorRegistry.register()   # daftarkan JDBC Sink connector (tabel sudah ada)
```

## 3. Jaminan keamanan terhadap SQL Server (read-only)

Ini poin paling penting: **proses konversi skema tidak pernah menulis apa pun ke SQL Server.**

- `schema_sync.py` dan `06-generate-postgres-ddl.py` hanya menjalankan `SELECT` ke `INFORMATION_SCHEMA.COLUMNS` (dan `cdc.change_tables` untuk daftar tabel). Tidak ada `INSERT`, `UPDATE`, `DELETE`, `ALTER`, atau DDL apa pun ke database SolarWinds.
- Semua `CREATE SCHEMA IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` dieksekusi **hanya di sisi PostgreSQL**.
- `CREATE TABLE IF NOT EXISTS` bersifat idempotent dan tidak pernah `DROP`/`ALTER` kolom yang sudah ada — dijalankan berulang kali (setiap restart container) aman, tidak menghapus data yang sudah masuk.
- Satu-satunya operasi yang menulis sesuatu ke SQL Server di seluruh pipeline ini adalah [scripts/01-enable-cdc.sql](../scripts/01-enable-cdc.sql) (`sp_cdc_enable_db` / `sp_cdc_enable_table`), dan itu **dijalankan sekali secara manual oleh Anda di SSMS**, bukan otomatis oleh aplikasi. Perintah itu sendiri adalah fitur bawaan SQL Server untuk CDC — membuat schema `cdc` beserta *change table* terpisah dan job SQL Agent, **tidak mengubah** tabel/data SolarWinds yang ada.

Ringkasnya: aplikasi Python (`cdc/app/*`) hanya pernah melakukan `SELECT`/`EXEC sys.fn_cdc_*` (fungsi baca) ke SQL Server, tidak pernah menulis.

## 4. Tabel pemetaan tipe data

| SQL Server | PostgreSQL | Catatan |
|---|---|---|
| `bigint` | `bigint` | |
| `int` | `integer` | |
| `smallint`, `tinyint` | `smallint` | Postgres tidak punya tipe 1-byte unsigned; `smallint` cukup menampung `tinyint` (0–255). |
| `bit` | `boolean` | |
| `decimal(p,s)`, `numeric(p,s)` | `numeric(p,s)` | Presisi & skala dipertahankan. |
| `money` | `numeric(19,4)` | |
| `smallmoney` | `numeric(10,4)` | |
| `float` | `double precision` | |
| `real` | `real` | |
| `date` | `date` | |
| `datetime`, `datetime2`, `smalldatetime` | `timestamp` | Tanpa timezone, sama seperti sumbernya. |
| `datetimeoffset` | `timestamptz` | |
| `time` | `time` | |
| `char(n)`, `varchar(n)`, `nchar(n)`, `nvarchar(n)` | `varchar(n)` | |
| `varchar(max)`, `nvarchar(max)`, `text`, `ntext` | `text` | |
| `uniqueidentifier` | `uuid` | |
| `binary(n)`, `varbinary(n)`, `image` | `bytea` | |
| `xml` | `xml` | |
| `rowversion` / `timestamp` (alias) | `bytea` | Ini kolom versi biner 8-byte, BUKAN kolom tanggal walau namanya "timestamp". |
| `sql_variant`, `geography`, `geometry`, `hierarchyid` | `text` | **Perlu review manual** — dipetakan ke `text` sebagai fallback aman karena tidak ada padanan langsung. `schema_sync.py` mencatat `WARNING` di log untuk tiap kolom seperti ini. |
| Tipe lain yang tidak dikenal | `text` | Fallback aman, dicatat sebagai `WARNING`. |

## 5. Aturan nama tabel & kolom (huruf besar/kecil)

[cdc/app/connector_registry.py](../cdc/app/connector_registry.py) membuat `table.name.format` dari `table.table.lower()` (nama tabel selalu lowercase), tapi **tidak** melakukan lowercase pada nama kolom — kunci JSON persis sama dengan nama kolom SQL Server aslinya (mis. `NodeID`, `IPAddress`), dan connector memakai `quote.identifiers=true`.

Karena itu `schema_sync.py` dan `06-generate-postgres-ddl.py` **sengaja**:
- Membuat nama tabel lowercase (mis. `solarwinds.nodes`), konsisten dengan yang dipakai JDBC Sink.
- Meng-quote nama kolom dengan huruf besar/kecil asli (mis. `"NodeID"`, `"IPAddress"`).

Kalau ini tidak konsisten, JDBC Sink akan menganggap kolom "belum ada" dan mencoba `auto.evolve` menambah kolom duplikat dengan nama ter-lowercase — dua kolom untuk data yang sama.

## 6. Batasan yang tetap perlu perhatian manual

- **Kolom baru dari upgrade modul SolarWinds** (NPM/SAM/NTA/IPAM/NCM menambah kolom di versi baru): `CONNECTOR_AUTO_EVOLVE=true` di `.env` akan tetap membuat kolom baru itu otomatis via JDBC Sink, tapi tipenya kembali ditebak dari JSON (masalah yang sama seperti di bagian 1, khusus untuk kolom yang baru itu saja). Jalankan ulang `scripts/06-generate-postgres-ddl.py` atau restart container `cdc` (schema_sync jalan lagi) setelah upgrade modul untuk menyamakan tipenya — schema_sync tidak melakukan `ALTER TABLE ADD COLUMN` otomatis untuk tabel yang sudah ada, hanya `CREATE TABLE IF NOT EXISTS` untuk tabel yang belum ada.
- **Tipe eksotis** (`sql_variant`, `geography`, `geometry`, `hierarchyid`) dipetakan ke `text` — cek log container (`docker-compose logs cdc | grep WARNING`) untuk tahu kolom mana yang terkena, lalu sesuaikan manual di PostgreSQL bila representasi teks tidak cukup untuk kebutuhan Anda.

## 7. Cara verifikasi

```bash
docker-compose logs -f cdc
# cari baris: "Schema sync applied for N table(s) in schema 'solarwinds'"
# cari baris berlevel WARNING untuk kolom yang perlu direview
```

```sql
-- di PostgreSQL, cek tipe kolom hasil sinkronisasi
\d solarwinds.nodes
```
