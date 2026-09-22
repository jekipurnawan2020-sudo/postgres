# Runbook Deployment: SolarWinds SQL Server → PostgreSQL

Urutan lengkap dari nol: pembuatan/penyesuaian akun di kedua sisi database, aktivasi CDC, sampai stack migrasi berjalan dan terverifikasi. Ikuti berurutan — setiap fase mengasumsikan fase sebelumnya sudah selesai.

Referensi terkait:
- [README.md](../README.md) — ringkasan arsitektur & operasional harian.
- [docs/SCHEMA-CONVERSION.md](SCHEMA-CONVERSION.md) — detail konversi tipe data (Fase 6 di sini merujuk ke situ).

## Tiga mesin yang terlibat

Runbook ini menyeberangi tiga lingkungan berbeda — setiap fase saya tandai mesin mana yang dipakai:

| Label | Mesin | OS | Dipakai untuk |
|---|---|---|---|
| 🪟 **SQLSRV** | Server SQL Server (SolarWinds) | Windows Server 2019 | SSMS, T-SQL admin (CDC, akun) |
| 🐧 **DOCKER** | Server PostgreSQL | Ubuntu (Postgres native + Docker Engine untuk kafka/kafka-connect/cdc) | `docker compose`, `psql`, deploy stack |
| 💻 **WORK** | Mesin kerja Anda sekarang (`c:\postgres`) | Windows | Edit kode, `git push`/`pull`, opsional jalankan script Python kalau ada akses jaringan langsung |

Karena OS berbeda, perintah shell di runbook ini beda gaya: blok berlabel `sql` dijalankan di SSMS (🪟 SQLSRV), blok `bash` dijalankan di terminal Ubuntu lewat SSH (🐧 DOCKER).

## Checklist ringkas

- [ ] Fase 0 — Akses jaringan & prasyarat OS terverifikasi
- [ ] Fase 1 — Akun SQL Server (admin one-time + service account `cdc_user`)
- [ ] Fase 2 — Akun PostgreSQL (`migration_user`) + akses dari Docker bridge
- [ ] Fase 3 — Discovery database SolarWinds
- [ ] Fase 4 — Aktifkan & verifikasi CDC
- [ ] Fase 5 — Siapkan control table PostgreSQL
- [ ] Fase 6 — (Opsional) Preview DDL skema target
- [ ] Fase 7 — Finalisasi `.env`
- [ ] Fase 8 — Strategi initial load (otomatis vs bulk dump untuk tabel besar)
- [ ] Fase 9 — Deploy stack Docker
- [ ] Fase 10 — Verifikasi end-to-end
- [ ] Fase 11 — Operasional & rollback

---

## Fase 0 — Akses jaringan & prasyarat OS

### 🐧 DOCKER → 🪟 SQLSRV (port 1433)

```bash
nc -zv <IP_SQLSERVER> 1433
# atau kalau nc tidak ada:
timeout 3 bash -c "cat < /dev/null > /dev/tcp/<IP_SQLSERVER>/1433" && echo "OPEN" || echo "CLOSED"
```

Kalau gagal, kemungkinan besar penyebabnya ada di sisi Windows (lanjut ke Fase 1), bukan di Ubuntu:

1. **TCP/IP protocol** sering **default mati** di SQL Server (terutama edisi Developer/Express) — harus diaktifkan manual lewat **SQL Server Configuration Manager** → SQL Server Network Configuration → Protocols for `<instance>` → TCP/IP → Enabled. Set juga **TCP Port statis `1433`** di tab IP Addresses (bagian `IPAll`), lalu **restart service SQL Server**.
2. **Windows Firewall** — buat inbound rule TCP 1433 dari IP server Ubuntu (🐧 DOCKER):
   ```powershell
   New-NetFirewallRule -DisplayName "SQL Server CDC (1433)" -Direction Inbound -Protocol TCP -LocalPort 1433 -RemoteAddress <IP_UBUNTU> -Action Allow
   ```
3. Kalau pakai *named instance* (bukan default), Anda butuh juga UDP 1434 (SQL Browser) terbuka, atau lebih simpel: pakai TCP port statis seperti langkah 1 dan set `SQLSERVER_PORT` di `.env` langsung ke port itu (menghindari dependency ke SQL Browser sama sekali — ini yang direkomendasikan).

### 🐧 DOCKER → PostgreSQL (localhost, sama mesin — port 5432)

```bash
nc -zv 127.0.0.1 5432
```

Postgres di sini **native** (bukan container), sedangkan kafka/kafka-connect/cdc **container**. Konektivitas container → Postgres native di host yang sama tidak otomatis "just work" seperti dua proses biasa di Linux — lihat catatan khusus di Fase 2.

---

## Fase 1 — Akun SQL Server (🪟 SQLSRV, via SSMS)

Ada **dua peran akun** yang berbeda, jangan disatukan:

| Akun | Dipakai untuk | Hak akses | Frekuensi pakai |
|---|---|---|---|
| Admin (existing) | Menjalankan `sp_cdc_enable_db`/`sp_cdc_enable_table` (Fase 4) | `sysadmin` atau `db_owner` | Sekali saat setup |
| `cdc_user` (service account) | Dipakai terus-menerus oleh container `cdc` di Ubuntu (`SQLSERVER_USER` di `.env`) | `db_datareader` — read-only | Berjalan 24/7 |

**Kenapa dipisah**: container `cdc` berjalan unattended di server Linux terpisah dan kredensialnya ada di `.env`. Memberi hak `sysadmin`/`db_owner` ke akun yang dipakai proses otomatis adalah risiko keamanan yang tidak perlu — service account ini secara desain cuma pernah melakukan `SELECT` (lihat [cdc/app/sqlserver.py](../cdc/app/sqlserver.py), [metadata.py](../cdc/app/metadata.py), [cdc_reader.py](../cdc/app/cdc_reader.py), [schema_sync.py](../cdc/app/schema_sync.py) — tidak ada satu pun `INSERT`/`UPDATE`/`ALTER` ke SQL Server di seluruh kode aplikasi).

### 1a. Wajib untuk skenario ini: aktifkan Mixed Mode Authentication

`cdc_user` di kode ini adalah **SQL Login** (koneksi pakai `UID`/`PWD` di connection string [sqlserver.py](../cdc/app/sqlserver.py), bukan Windows/AD account) — masuk akal karena yang connect adalah container Linux di Ubuntu, bukan mesin domain Windows. Ini **hanya bisa jalan** kalau instance SQL Server Anda diset **"SQL Server and Windows Authentication mode"** (mixed mode), bukan "Windows Authentication mode" saja (yang jadi default rekomendasi keamanan banyak DBA).

Cek & ubah lewat SSMS: klik kanan server → Properties → Security → pilih **SQL Server and Windows Authentication mode** → restart service SQL Server kalau tadinya di mode lain.

### 1b. Kalau belum ada admin login yang bisa dipakai

```sql
SELECT IS_SRVROLEMEMBER('sysadmin') AS is_sysadmin,
       IS_ROLEMEMBER('db_owner') AS is_db_owner;
```

Kalau salah satu `1`, akun itu bisa dipakai untuk Fase 4. Tidak perlu buat akun admin baru.

### 1c. Buat service account `cdc_user`

```sql
USE [master];
GO
CREATE LOGIN cdc_user WITH PASSWORD = 'GANTI_DENGAN_PASSWORD_KUAT', CHECK_POLICY = ON;
GO

USE [SolarWindsOrion];
GO
CREATE USER cdc_user FOR LOGIN cdc_user;
GO
ALTER ROLE db_datareader ADD MEMBER cdc_user;
GO
```

Kalau Anda **sudah punya akun existing** yang ingin dipakai ulang: cukup jalankan bagian `ALTER ROLE db_datareader ADD MEMBER <nama_login_existing>;` pada database `SolarWindsOrion` untuk login tersebut, dan pastikan login itu SQL Login (bukan Windows-only) — kalau login existing Anda tipe Windows/AD, container Linux **tidak bisa** memakainya (tidak ada domain join), harus tetap SQL Login baru seperti di atas.

**Kenapa `db_datareader` cukup**: [scripts/01-enable-cdc.sql](../scripts/01-enable-cdc.sql) mengaktifkan capture instance dengan `@role_name = NULL`, artinya SQL Server **tidak** memberlakukan gating role khusus untuk data CDC — siapa pun yang punya hak `SELECT` ke tabel sumber otomatis juga bisa membaca `cdc.fn_cdc_get_all_changes_*` untuk tabel itu.

**Kalau ternyata kurang** (error permission saat container `cdc` jalan), fallback:

```sql
USE [SolarWindsOrion];
GO
GRANT SELECT ON SCHEMA::cdc TO cdc_user;
GO
```

### 1d. Verifikasi (dari mana pun yang bisa konek ke SQL Server dengan akun `cdc_user`)

```sql
SELECT TOP 1 * FROM cdc.change_tables;   -- boleh kosong (CDC belum aktif di Fase 4), tapi TIDAK boleh error permission
SELECT sys.fn_cdc_get_max_lsn();          -- harus jalan tanpa error
```

---

## Fase 2 — Akun PostgreSQL & akses dari Docker (🐧 DOCKER)

### 2a. Buat role `migration_user`

Jalankan sebagai superuser/admin PostgreSQL yang sudah ada, **satu kali**, lewat `psql` di server Ubuntu:

```bash
sudo -u postgres psql
```

```sql
-- kalau database migratedb belum ada
CREATE ROLE migration_user WITH LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_KUAT';
CREATE DATABASE migratedb OWNER migration_user;
```

```sql
-- kalau migratedb sudah ada, dipakai bareng aplikasi lain
CREATE ROLE migration_user WITH LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_KUAT';
GRANT CONNECT ON DATABASE migratedb TO migration_user;
GRANT CREATE ON DATABASE migratedb TO migration_user;
```

Alternatif least-privilege (tanpa `CREATE` di level database — DBA pre-create schema, serahkan ownership):

```sql
CREATE ROLE migration_user WITH LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_KUAT';
GRANT CONNECT ON DATABASE migratedb TO migration_user;
\connect migratedb
CREATE SCHEMA IF NOT EXISTS solarwinds AUTHORIZATION migration_user;
CREATE SCHEMA IF NOT EXISTS migration_control AUTHORIZATION migration_user;
```

### 2b. Penting: PostgreSQL native + container di host yang sama TIDAK otomatis saling lihat

Ini titik yang paling sering bikin stuck di topologi Anda (Postgres native, kafka-connect/cdc container, satu mesin Ubuntu yang sama). Dua hal wajib disiapkan di sisi PostgreSQL:

**i. `listen_addresses` harus mendengarkan interface yang dipakai, bukan cuma `localhost`.**

Edit `postgresql.conf` (biasanya `/etc/postgresql/<versi>/main/postgresql.conf`):

```
listen_addresses = '*'
```

(atau spesifik ke IP LAN server, mis. `10.52.132.139`, kalau tidak mau membuka ke semua interface).

**ii. `pg_hba.conf` harus mengizinkan koneksi dari subnet bridge Docker**, bukan cuma dari `127.0.0.1`. Karena kafka-connect dan cdc berjalan sebagai container di *bridge network* Docker (lihat `networks.solarwonds` di [docker-compose.yml](../docker-compose.yml)), koneksi ke Postgres native akan datang dari IP privat Docker, bukan `127.0.0.1` dan belum tentu identik dengan IP LAN host.

Cari subnet bridge Docker-nya:

```bash
docker network inspect postgres_solarwonds --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
# atau kalau stack belum pernah naik, subnet default bridge:
ip addr show docker0
```

Tambahkan baris di `pg_hba.conf` (biasanya `/etc/postgresql/<versi>/main/pg_hba.conf`), sesuaikan subnet dengan hasil di atas:

```
# Docker bridge network (kafka-connect, cdc)
host    migratedb    migration_user    172.18.0.0/16    scram-sha-256
```

Lalu reload (tidak perlu restart service):

```bash
sudo systemctl reload postgresql
```

**iii. Firewall Ubuntu (`ufw`)** kalau aktif — izinkan port 5432 dari subnet Docker yang sama:

```bash
sudo ufw allow from 172.18.0.0/16 to any port 5432 proto tcp
```

### 2c. Verifikasi

```bash
psql -h 127.0.0.1 -p 5432 -U migration_user -d migratedb -c "SELECT current_user, current_database();"
```

Verifikasi **dari dalam container** juga penting (ini yang benar-benar dipakai nanti) — setelah Fase 8, container manapun bisa dites:

```bash
docker compose exec cdc python -c "import psycopg,os; c=psycopg.connect(host=os.environ['POSTGRES_HOST'],port=os.environ['POSTGRES_PORT'],dbname=os.environ['POSTGRES_DB'],user=os.environ['POSTGRES_USER'],password=os.environ['POSTGRES_PASSWORD']); print('OK', c.info.status)"
```

---

## Fase 3 — Discovery database SolarWinds (🪟 SQLSRV, via SSMS)

Login pakai akun admin (Fase 1b), jalankan:

```
scripts/00-discovery-database.sql
```

Catat hasilnya: jumlah tabel, tabel besar (row count tinggi — jadi perhatian untuk durasi initial load), dan daftar **tabel tanpa primary key** (bagian 5 output) — tabel-tabel ini **tidak akan** ikut ter-CDC di Fase 4.

---

## Fase 4 — Aktifkan & verifikasi CDC (🪟 SQLSRV, via SSMS)

Login pakai akun **admin** (bukan `cdc_user`).

1. Jalankan `scripts/01-enable-cdc.sql` di database `SolarWindsOrion`.
2. Verifikasi:

```
scripts/02-check-tables.sql          -- daftar semua base table
scripts/03-check-primary-keys.sql    -- tabel & kolom PK-nya
scripts/04-check-cdc.sql             -- capture instance yang aktif
```

3. Pastikan **SQL Server Agent** service statusnya `Running` (Windows Services / SSMS → SQL Server Agent) — CDC capture job dan cleanup job jalan lewat Agent. Kalau Agent mati, `cdc.change_tables` tetap terisi tapi data perubahan baru tidak masuk ke change table.

```sql
EXEC msdb.dbo.sp_help_job @job_name = N'%capture%';
```

---

## Fase 5 — Siapkan control table PostgreSQL (🐧 DOCKER)

```bash
psql -h 127.0.0.1 -p 5432 -U migration_user -d migratedb -f scripts/05-create-postgres-control.sql
```

Ini membuat `migration_control.cdc_checkpoint` lebih awal untuk validasi permission (aplikasi sebenarnya juga membuatnya sendiri saat startup lewat [checkpoint.py](../cdc/app/checkpoint.py), jadi langkah ini bersifat validasi, bukan wajib mutlak).

---

## Fase 6 — (Opsional) Preview DDL skema target

Skema tabel target (`solarwinds.<tabel>`) sekarang dibuat **otomatis** oleh [cdc/app/schema_sync.py](../cdc/app/schema_sync.py) saat container `cdc` start — lihat [docs/SCHEMA-CONVERSION.md](SCHEMA-CONVERSION.md). Kalau Anda ingin preview dulu:

**Cara yang direkomendasikan — lewat container di 🐧 DOCKER** (image `cdc` sudah punya ODBC Driver 18 + pyodbc + psycopg terpasang, tidak perlu instal apa pun tambahan di Ubuntu bare-metal):

```bash
docker compose build cdc
docker compose run --rm -v "$(pwd)/scripts/generated:/app/scripts/generated" cdc \
  python scripts/06-generate-postgres-ddl.py
```

File hasilnya muncul di `scripts/generated/` pada host Ubuntu (lewat bind mount di atas).

**Alternatif — dari 💻 WORK (mesin Windows Anda saat ini)**, kalau mesin ini punya akses jaringan langsung ke SQL Server *dan* PostgreSQL, dan sudah terinstal ODBC Driver 18 for SQL Server (seperti yang dipakai `testing-cdc-docker-sql.py`):

```powershell
pip install pyodbc "psycopg[binary]" python-dotenv
python scripts/06-generate-postgres-ddl.py
```

Review file hasilnya, terutama baris `-- WARNING` (tipe data yang perlu penyesuaian manual).

---

## Fase 7 — Finalisasi `.env`

Edit di 💻 WORK, lalu commit/pull ke 🐧 DOCKER (jangan copy manual file mentah dari Windows ke Ubuntu di luar git — lihat catatan CRLF di bawah).

```
SQLSERVER_HOST=<IP SQL Server>
SQLSERVER_DATABASE=SolarWindsOrion
SQLSERVER_USER=cdc_user
SQLSERVER_PASSWORD=<password dari Fase 1c>

POSTGRES_HOST=127.0.0.1        # Postgres native di mesin yang sama dengan Docker -> localhost, BUKAN IP LAN
POSTGRES_DB=migratedb
POSTGRES_USER=migration_user
POSTGRES_PASSWORD=<password dari Fase 2a>

TARGET_SCHEMA=solarwinds
INITIAL_LOAD_ENABLED=true    # false kalau hanya mau capture perubahan baru, tanpa snapshot histori
```

**Soal `POSTGRES_HOST`**: karena Postgres native dan Docker ada di **mesin yang sama** (🐧 DOCKER), `127.0.0.1` lebih andal daripada IP LAN publik server (10.52.132.139) — tidak bergantung pada hairpin NAT Docker yang perilakunya bisa beda-beda antar versi Docker Engine. Ini konsisten dengan pengaturan `pg_hba.conf`/`listen_addresses` di Fase 2b yang mengizinkan subnet bridge Docker menjangkau `listen_addresses` di semua interface — `127.0.0.1` dari dalam container tetap melewati bridge (bukan loopback container itu sendiri), jadi tetap butuh Fase 2b, hanya saja penulisan hostname-nya lebih stabil. Kalau setelah dicoba `127.0.0.1` tidak konek dari dalam container, ganti ke IP LAN host Ubuntu sebagai fallback.

**Wajib diganti**: kedua `*_PASSWORD` yang masih `CHANGE_ME`. Jangan commit `.env` — sudah dikecualikan via `.gitignore`, isi manual di 🐧 DOCKER langsung kalau tidak mau lewat git sama sekali untuk file rahasia ini.

**Catatan CRLF**: repo ini sudah punya [.gitattributes](../.gitattributes) (`* text=auto eol=lf`) supaya file dinormalisasi ke LF saat commit, terlepas dari `core.autocrlf` di mesin Windows Anda. Tetap **deploy ke Ubuntu lewat `git clone`/`git pull`**, jangan `scp`/copy manual folder kerja Windows — itu akan membawa CRLF apa adanya dan berpotensi bikin script/Dockerfile rewel di Linux.

---

## Fase 8 — Strategi initial load: otomatis vs bulk dump manual

Karena target PostgreSQL masih kosong, pertanyaannya: perlu dump manual dari SQL Server dulu, atau biarkan pipeline yang isi?

### Perkiraan dari ukuran `.mdf`: 980 MB → kemungkinan besar tidak perlu jalur bulk

Ukuran file data (`.mdf`) SolarWinds yang Anda lihat: **980 MB**. Ini cukup untuk membuat keputusan awal tanpa menunggu apa pun.

**Perhitungan kasar:**
- 980 MB adalah ruang yang **dialokasikan** SQL Server ke `.mdf`, bukan otomatis sama dengan data terpakai — SQL Server lazim mengalokasikan ruang kosong yang belum terisi di dalamnya, jadi data aktual kemungkinan **lebih kecil** dari 980 MB, bukan lebih besar.
- Index & overhead katalog biasanya makan 30-50% dari ukuran tabel pada skema semacam SolarWinds (banyak index untuk mendukung query dashboard) → data tabel murni diperkirakan sekitar 500-700 MB.
- Baris rata-rata tabel SolarWinds (campuran `int`/`varchar`/`datetime`/`float`) biasanya 150-400 byte → estimasi **total baris di SELURUH tabel sekitar 1,5-4 juta baris**, bukan puluhan/ratusan juta.
- Skenario terburuk (satu tabel time-series sangat sempit, mis. `InterfaceID + DateTime + float`, ~30-50 byte/baris, memakai porsi besar dari 700 MB) paling banter menghasilkan **satu tabel belasan juta baris** — itu pun kasus ekstrem, bukan tipikal.

**Kesimpulan**: 980 MB adalah database SolarWinds yang **kecil** — instalasi produksi SolarWinds yang sudah lama jalan dengan modul lengkap biasanya puluhan sampai ratusan GB. Kemungkinan ini instalasi baru, retention period pendek, atau modul aktifnya terbatas (NPM inti saja, tanpa riwayat panjang SAM/NTA).

**Rekomendasi saya: skip jalur bulk dump (pgloader/bcp) sepenuhnya, pakai mekanisme initial load otomatis pipeline untuk SEMUA tabel.** Di skala ini, initial load lewat Kafka (sudah batched-flush, bukan per-baris — lihat [producer.py](../cdc/app/producer.py)) realistis selesai dalam hitungan menit, bukan jam. Kompleksitas tambahan bulk-copy (instal pgloader, seed LSN manual, risiko mismatch tipe data dari pgloader) tidak sepadan manfaatnya di ukuran data segini.

**Tapi tetap verifikasi, jangan cuma percaya estimasi** — dua alasan konkret:
1. Estimasi di atas asumsi kasar berbasis rata-rata; bisa meleset kalau distribusi baris antar tabel timpang.
2. **Kemungkinan modul NTA (NetFlow Traffic Analyzer) menyimpan flow data di database SQL Server yang TERPISAH**, bukan di `SolarWinds` yang sama — kalau modul itu aktif dan datanya perlu ikut dimigrasikan, 980 MB ini **tidak mencakupnya sama sekali**. Cek lewat SSMS → Object Explorer → Databases, lihat apakah ada database lain bernama sejenis `SolarWindsNTA`/`NTA`. Kalau ada dan perlu dimigrasikan, itu butuh instance pipeline kedua yang menunjuk `SQLSERVER_DATABASE` berbeda — di luar scope estimasi 980 MB ini.

**Implementasi/langkah konkretnya**: jalankan Fase 3 (`scripts/00-discovery-database.sql`) sebagai konfirmasi murah (hitungan detik) sebelum deploy.
- Kalau hasilnya cocok dengan estimasi ini (tidak ada tabel dengan row count jutaan+, tidak ada database NTA terpisah yang perlu ikut) → lanjut langsung ke Fase 9 dengan `INITIAL_LOAD_ENABLED=true` untuk semua tabel (nilai default yang sudah ada di contoh `.env` Fase 7), **lewati bagian "jalur bulk dump" di bawah sepenuhnya**.
- Kalau ternyata ada tabel dengan row count jauh di luar dugaan, atau ketemu database NTA terpisah yang perlu ikut dimigrasikan → baru pertimbangkan mekanisme bulk yang dijelaskan di bawah, khusus untuk tabel/database yang bermasalah itu saja (tidak perlu diterapkan ke semua tabel).

### Mekanisme initial load otomatis (opsi default — kemungkinan ini yang dipakai di kasus Anda)

Pipeline ini **sudah otomatis** melakukan initial load. Kalau `INITIAL_LOAD_ENABLED=true` (Fase 7), begini alurnya per tabel saat container `cdc` pertama kali jalan (lihat `publish_initial_load()` di [main.py](../cdc/app/main.py)):

1. Rekam `sys.fn_cdc_get_max_lsn()` saat itu sebagai titik potong yang konsisten.
2. `SELECT * FROM [schema].[table]` — seluruh baris di-stream lewat Kafka ke PostgreSQL (upsert lewat JDBC Sink).
3. Simpan LSN dari langkah 1 sebagai checkpoint tabel itu di `migration_control.cdc_checkpoint`.
4. Mulai baca CDC incremental dari LSN tersebut — otomatis menyambung, tidak ada celah maupun duplikasi data yang berubah selama proses snapshot berlangsung.

Ini satu mekanisme untuk snapshot awal *dan* perubahan berkelanjutan, tanpa koordinasi manual — untuk kebanyakan tabel SolarWinds (inventori/konfigurasi: `Nodes`, `Interfaces`, `Volumes`, `AlertConfigurations`, dst) ini sudah cukup dan paling "smooth".

### Jalur bulk dump (fallback) — kemungkinan besar tidak Anda perlukan

Bagian ini berlaku hanya kalau Fase 3 membuktikan estimasi di atas salah untuk tabel tertentu. Untuk tabel **volume tinggi** — biasanya tabel time-series SolarWinds (`InterfaceTraffic`, `ResponseTime`, `CPULoad`, `APM_AvailabilityHistory`, tabel NetFlow, `Events`) — initial load lewat Kafka row-by-row kalah jauh dibanding bulk-copy native:

- Tiap baris → JSON → produce ke Kafka → consume oleh JDBC Sink → `INSERT`. Overhead per baris jauh lebih besar daripada `bcp`/`COPY` yang bulk.
- Initial load jutaan baris lewat jalur ini bisa berjam-jam, dan `SELECT *` yang panjang membebani SQL Server production selagi SolarWinds tetap live dipakai.

**Rekomendasi**: jangan putuskan sekarang untuk semua tabel sekaligus. Lihat dulu hasil row count dari Fase 3 (`scripts/00-discovery-database.sql`, bagian 3). Tabel dengan row count besar (jutaan+) — pertimbangkan mekanisme bulk di bawah. Tabel kecil/menengah biarkan pakai initial load bawaan (Opsi A). Boleh dicampur per tabel, tidak harus seragam.

### Mekanisme bulk dump + handoff mulus ke CDC (untuk tabel besar) — 🐧 DOCKER

Prinsipnya: ambil snapshot data sekali lewat tool bulk-copy (jauh lebih cepat dari jalur Kafka), lalu "titipkan" checkpoint CDC persis di titik snapshot itu supaya pipeline lanjut dari sana tanpa initial load Kafka dan tanpa celah/duplikasi data.

1. **Pastikan CDC sudah aktif** (Fase 4) **sebelum** dump — supaya SQL Server sudah merekam perubahan sejak saat itu, tidak ada window kosong.
2. **Catat titik potong LSN** tepat sebelum/selagi dump, per capture instance:
   ```sql
   -- 🪟 SQLSRV
   SELECT sys.fn_cdc_get_max_lsn() AS snapshot_lsn;
   ```
   LSN ini `binary(10)` — simpan dalam bentuk hex uppercase (format yang sama dipakai `current_lsn()` di [sqlserver.py](../cdc/app/sqlserver.py)):
   ```sql
   SELECT UPPER(CONVERT(varchar(20), sys.fn_cdc_get_max_lsn(), 2)) AS snapshot_lsn_hex;
   ```
3. **Bulk export dari SQL Server ke PostgreSQL** — pilih salah satu, keduanya dijalankan dari 🐧 DOCKER (Ubuntu):
   - **pgloader** — paling praktis untuk migrasi MSSQL→Postgres, satu perintah men-transfer skema+data langsung lewat FreeTDS tanpa file perantara:
     ```bash
     sudo apt install pgloader
     pgloader mssql://cdc_user:<password>@<IP_SQLSERVER>/SolarWindsOrion?tables=InterfaceTraffic \
       postgresql://migration_user:<password>@127.0.0.1/migratedb
     ```
     Catatan: pgloader membuat tabelnya sendiri dengan pemetaan tipe versinya sendiri — untuk tabel yang di-backfill lewat pgloader, **jangan** biarkan `schema_sync.py` membuat ulang tabel itu duluan (tidak masalah kalau urutannya pgloader dulu baru start stack, karena `CREATE TABLE IF NOT EXISTS` di `schema_sync.py` akan otomatis skip tabel yang sudah ada).
   - **bcp** (built-in tools SQL Server, jalan dari 🪟 SQLSRV) export ke file `.csv`/native format, salin ke Ubuntu, lalu `psql \copy` atau `COPY ... FROM` untuk impor — lebih manual tapi tidak butuh instalasi tool tambahan di Ubuntu.
4. **Seed checkpoint** — masukkan LSN dari langkah 2 ke `migration_control.cdc_checkpoint` untuk `capture_instance` tabel itu **sebelum** `docker compose up` (Fase 9):
   ```bash
   psql -h 127.0.0.1 -U migration_user -d migratedb -c "
   INSERT INTO migration_control.cdc_checkpoint (capture_instance, start_lsn)
   VALUES ('<capture_instance_tabel>', '<snapshot_lsn_hex dari langkah 2>')
   ON CONFLICT (capture_instance) DO UPDATE SET start_lsn = EXCLUDED.start_lsn, updated_at = now();"
   ```
   Nama `capture_instance` persis seperti di `cdc.change_tables` (cek lewat `scripts/04-check-cdc.sql`, biasanya `dbo_<NamaTabel>`).

   Dengan checkpoint ini terisi, `main.py` melihat `previous_lsn` tabel tersebut sudah ada (bukan `None`), sehingga initial load Kafka **otomatis dilewati** untuk tabel ini — pipeline langsung lanjut CDC incremental dari LSN yang di-seed. Tabel lain yang tidak di-seed tetap jalan initial load otomatis seperti biasa.

Kalau Anda mau jalan opsi bulk ini untuk tabel tertentu, beri tahu saya nama tabelnya (setelah lihat hasil Fase 3) — saya bisa buatkan script kecil untuk otomasi langkah 2 & 4 (catat LSN + seed checkpoint) supaya tidak salah ketik LSN secara manual.

---

## Fase 9 — Deploy stack (🐧 DOCKER)

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs -f cdc
```

Tunggu sampai muncul log berurutan seperti ini (normal, tidak perlu campur tangan):

```
... Schema sync applied for N table(s) in schema 'solarwinds'
... Registered N Kafka Connect sink connectors
... CDC reader started for N capture instances
```

---

## Fase 10 — Verifikasi end-to-end (🐧 DOCKER, kecuali disebutkan lain)

1. **Connector JDBC Sink jalan**:
   ```bash
   curl http://localhost:8083/connectors
   curl http://localhost:8083/connectors/<nama-connector>/status
   ```
   Status tiap connector & task harus `RUNNING`, bukan `FAILED`.

2. **Checkpoint maju**:
   ```bash
   psql -h 127.0.0.1 -U migration_user -d migratedb -c \
     "SELECT * FROM migration_control.cdc_checkpoint ORDER BY updated_at DESC;"
   ```

3. **Data konsisten** — bandingkan row count tabel kecil dulu:
   ```sql
   -- 🪟 SQLSRV, SSMS
   SELECT COUNT(*) FROM dbo.Nodes;
   ```
   ```bash
   # 🐧 DOCKER
   psql -h 127.0.0.1 -U migration_user -d migratedb -c "SELECT COUNT(*) FROM solarwinds.nodes;"
   ```

4. **Tipe kolom benar** (bukan semua jadi `text`):
   ```bash
   psql -h 127.0.0.1 -U migration_user -d migratedb -c "\d solarwinds.nodes"
   ```

5. **Update/delete tersampaikan** — ubah satu baris uji di SQL Server (🪟 SQLSRV), tunggu `CDC_POLL_INTERVAL` (default 1 detik) + waktu propagasi Kafka Connect, cek nilainya berubah di PostgreSQL (🐧 DOCKER).

---

## Fase 11 — Operasional & rollback

- Monitoring harian (🐧 DOCKER): `docker compose logs -f cdc`, `docker compose logs -f kafka-connect`, cek `migration_control.cdc_checkpoint`.
- **Jangan** hapus volume `solarwonds-kafka-data` atau tabel checkpoint selagi pipeline berjalan — akan menghilangkan posisi resume.
- Kalau perlu berhenti sementara: `docker compose stop` (bukan `down -v`, supaya volume tetap ada). Saat `docker compose up` lagi, pipeline lanjut dari checkpoint terakhir.
- Kalau perlu mengulang initial load satu tabel dari nol: hapus baris capture instance tabel itu dari `migration_control.cdc_checkpoint`, restart container `cdc`.
- SQL Server sisi source **tidak pernah** diubah oleh operasional harian pipeline ini (lihat jaminan read-only di [docs/SCHEMA-CONVERSION.md](SCHEMA-CONVERSION.md) bagian 3) — aman dijalankan berdampingan dengan SolarWinds yang tetap production-live di Windows Server 2019.
