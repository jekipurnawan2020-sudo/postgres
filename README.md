# SolarWinds SQL Server 2019 to PostgreSQL Migration

Stack migrasi:

`SQL Server 2019 (SolarWinds) -> Python CDC Reader -> Kafka -> Kafka Connect JDBC Sink -> PostgreSQL on-premise`

Semua service migrasi berjalan di Docker pada host yang memiliki akses jaringan ke SQL Server dan PostgreSQL. Nilai koneksi, password, nama database, dan kebijakan migration berada di `.env`.

Topologi acuan: SQL Server (SolarWinds) di **Windows Server 2019**, PostgreSQL native + Docker Engine (host `kafka`/`kafka-connect`/`cdc`) di **Ubuntu**, satu mesin yang sama dengan PostgreSQL. Perintah shell di dokumen ini (`bash`) dijalankan di server Ubuntu tersebut. Untuk runbook lengkap dari nol (pembuatan akun, aktivasi CDC, sampai verifikasi) lihat [docs/DEPLOYMENT-RUNBOOK.md](docs/DEPLOYMENT-RUNBOOK.md).

## Prasyarat

- Docker Engine dengan Compose V2, terpasang di server Ubuntu yang sama dengan PostgreSQL.
- Host Docker dapat terhubung ke SQL Server 2019 pada port `1433` dan ke PostgreSQL pada port `5432`.
- Akun SQL Server memiliki hak `sysadmin` atau hak yang diperlukan untuk `sp_cdc_enable_db` dan `sp_cdc_enable_table`.
- Akun PostgreSQL dapat membuat schema/table target dan tabel `migration_control.cdc_checkpoint`.
- Semua tabel yang dimigrasikan memiliki primary key. Tabel tanpa primary key tidak akan diaktifkan CDC-nya oleh [scripts/01-enable-cdc.sql](scripts/01-enable-cdc.sql) dan tidak aman diproses sebagai update/delete.

## Konfigurasi `.env`

Sesuaikan minimal:

- `SQLSERVER_HOST`, `SQLSERVER_PORT`, `SQLSERVER_DATABASE=SolarWindsOrion26`, `SQLSERVER_USER`, `SQLSERVER_PASSWORD`.
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
- `KAFKA_ADVERTISED_HOST` jika Kafka diakses dari host lain.
- `TARGET_SCHEMA` untuk schema tujuan PostgreSQL.

Jangan commit `.env` berisi password asli. `.gitignore` sudah mengecualikan file tersebut.

## Urutan deployment

### 1. Discovery & validasi akses source

Di SQL Server jalankan [scripts/00-discovery-database.sql](scripts/00-discovery-database.sql) untuk melihat daftar tabel, jumlah baris, dan tabel yang **tidak** punya primary key (tabel ini tidak akan ikut CDC). Lanjutkan dengan [scripts/02-check-tables.sql](scripts/02-check-tables.sql) dan [scripts/03-check-primary-keys.sql](scripts/03-check-primary-keys.sql) untuk memastikan tabel yang diperlukan terlihat dan memiliki primary key.

### 2. Aktifkan CDC

Di database `SolarWindsOrion26`, jalankan [scripts/01-enable-cdc.sql](scripts/01-enable-cdc.sql). Script ini:

1. Mengaktifkan CDC pada database.
2. Menemukan semua tabel user yang memiliki primary key.
3. Mengaktifkan capture instance untuk tabel yang belum aktif.

Verifikasi dengan [scripts/04-check-cdc.sql](scripts/04-check-cdc.sql). Jika hanya sebagian tabel yang boleh dimigrasikan, ubah query cursor pada `01-enable-cdc.sql` sebelum dijalankan.

### 3. Siapkan PostgreSQL

Jalankan [scripts/05-create-postgres-control.sql](scripts/05-create-postgres-control.sql) pada database target. Service CDC juga menjalankan `CREATE SCHEMA IF NOT EXISTS` dan `CREATE TABLE IF NOT EXISTS` saat startup, tetapi menjalankan script secara eksplisit membantu validasi permission lebih awal.

### 4. Skema tabel target (otomatis)

Setiap kali container `cdc` start, [cdc/app/schema_sync.py](cdc/app/schema_sync.py) membaca metadata kolom dari SQL Server (read-only, `SELECT` ke `INFORMATION_SCHEMA` saja) dan membuat tabel PostgreSQL dengan tipe data yang benar (`NUMERIC`, `TIMESTAMP`, `UUID`, dst) sebelum Kafka Connect mulai menulis data — bukan hasil tebakan otomatis JDBC Sink dari JSON tanpa schema. Tidak ada langkah manual yang wajib di sini.

Kalau Anda ingin **preview** DDL-nya sebelum stack pertama kali dinyalakan, jalankan [scripts/06-generate-postgres-ddl.py](scripts/06-generate-postgres-ddl.py) dari host. Detail lengkap pemetaan tipe data, jaminan bahwa proses ini tidak pernah menulis apa pun ke SQL Server, dan cara menangani kolom bertipe khusus ada di [docs/SCHEMA-CONVERSION.md](docs/SCHEMA-CONVERSION.md).

### 5. Start stack

```bash
docker-compose up -d --build
docker-compose ps
docker-compose logs -f cdc
```

Service CDC akan:

1. Membaca capture instance dari `cdc.change_tables`.
2. Menemukan primary key source dari metadata SQL Server.
3. Membuat topic `solarwinds.<schema>.<table>`.
4. Membuat/menyinkronkan tabel target PostgreSQL dengan tipe data yang benar ([schema_sync.py](cdc/app/schema_sync.py)).
5. Menunggu Kafka Connect REST siap lalu membuat atau memperbarui satu JDBC sink connector per tabel.
6. Menjalankan initial load jika `INITIAL_LOAD_ENABLED=true`.
7. Menyimpan LSN terakhir yang sukses dipublish di PostgreSQL.
8. Poll perubahan CDC berikutnya secara berulang.

Initial load mengambil `max_lsn` lebih dulu, mengirim snapshot, lalu membaca CDC mulai dari LSN setelah snapshot. Dengan demikian perubahan yang terjadi saat snapshot berlangsung tidak hilang dan data snapshot tidak dikirim ulang dari LSN minimum.

## Semantik data

- Insert dan update-after dikirim sebagai JSON datar.
- Primary key dikirim sebagai Kafka key JSON.
- JDBC Sink memakai `upsert` dan `pk.mode=record_key`.
- Delete dikirim sebagai Kafka tombstone (value pesan benar-benar `null`, bukan string `"null"`) dan diterapkan oleh JDBC Sink lewat `behavior.on.null.values=delete`.
- Producer melakukan `flush()` sekali per batch (bukan per baris) sebelum checkpoint disimpan, supaya throughput initial load/CDC tidak dibatasi oleh round-trip Kafka per pesan. Granularitas checkpoint pada incremental CDC jadi per-batch (maksimal `CDC_BATCH_SIZE` baris), bukan per-baris seperti sebelumnya.
- Crash di antara publish dan checkpoint dapat menghasilkan publish ulang (sampai maksimal satu batch), tetapi upsert/delete bersifat idempotent pada target sehingga aman diulang.
- Checkpoint hanya maju setelah seluruh batch berhasil di-flush ke Kafka.

## Monitoring dan troubleshooting

```bash
docker-compose logs -f cdc
docker-compose logs -f kafka-connect
curl http://localhost:8083/connectors
curl http://localhost:8083/connectors/<connector-name>/status
```

Untuk melihat checkpoint:

```sql
SELECT * FROM migration_control.cdc_checkpoint ORDER BY updated_at DESC;
```

Jangan menghapus volume `solarwonds-kafka-data` atau tabel checkpoint saat CDC masih berjalan. Menghapusnya dapat menyebabkan offset/checkpoint hilang dan memerlukan prosedur replay atau rekonsiliasi.

## Connector manual

Jika connector perlu dibuat manual, generator tersedia di [connectors/generate_connectors.py](connectors/generate_connectors.py). Namun pada deployment normal `REGISTER_CONNECTORS=true` membuat connector otomatis dari metadata source, sehingga tidak perlu mengisi daftar tabel secara manual.
