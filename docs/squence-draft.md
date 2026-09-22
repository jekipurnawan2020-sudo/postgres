# Sequence draft — setup akun migrasi

Catatan kerja ringkas (perintah siap-pakai). Penjelasan lengkap kenapa tiap langkah ada di [docs/DEPLOYMENT-RUNBOOK.md](DEPLOYMENT-RUNBOOK.md) Fase 1 & 2.

## SSMS (offline installer layout, kalau perlu)

```
vs_SSMS.exe --layout C:\SSMS_Layout --all
```

## 1. SQL Server — 🪟 SQLSRV, via SSMS

### 1a. Cek dulu sebelum bikin apa pun

```sql
-- akun admin yang lagi login ini punya hak cukup untuk enable CDC?
SELECT IS_SRVROLEMEMBER('sysadmin') AS is_sysadmin,
       IS_ROLEMEMBER('db_owner')    AS is_db_owner;

-- mode autentikasi harus Mixed (SQL Server + Windows), cek lewat SSMS:
-- klik kanan server > Properties > Security > "Server authentication"
-- kalau masih "Windows Authentication mode" saja, cdc_user (SQL login) TIDAK akan bisa login

-- login cdc_user sudah ada belum? (hindari error kalau create ulang)
SELECT name, type_desc, is_disabled, create_date
FROM sys.server_principals
WHERE name = 'cdc_user';

-- daftar semua SQL login yang ada di server ini (bukan Windows/AD account)
SELECT name, type_desc, is_disabled, create_date
FROM sys.server_principals
WHERE type = 'S'
ORDER BY name;
```

### 1b. Buat service account `cdc_user` (sekali saja)

```sql
USE [master];
GO
CREATE LOGIN cdc_user WITH PASSWORD = 'GANTI_DENGAN_PASSWORD_KUAT', CHECK_POLICY = ON;
GO

USE [SolarWinds];
GO
CREATE USER cdc_user FOR LOGIN cdc_user;
GO
ALTER ROLE db_datareader ADD MEMBER cdc_user;
GO
```

Fallback kalau `db_datareader` ternyata kurang (error permission saat container `cdc` jalan):

```sql
USE [SolarWinds];
GO
GRANT SELECT ON SCHEMA::cdc TO cdc_user;
GO
```

### 1c. Cek user & role setelah dibuat

```sql
-- role database yang dipegang cdc_user di SolarWinds
USE [SolarWinds];
GO
SELECT dp.name AS user_name, dp.type_desc,
       STRING_AGG(rp.name, ', ') AS roles
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members drm ON drm.member_principal_id = dp.principal_id
LEFT JOIN sys.database_principals rp ON rp.principal_id = drm.role_principal_id
WHERE dp.name = 'cdc_user'
GROUP BY dp.name, dp.type_desc;

-- cdc_user bisa baca metadata & fungsi CDC? (jalankan login SEBAGAI cdc_user)
SELECT TOP 1 * FROM cdc.change_tables;   -- boleh kosong (CDC belum aktif di Fase 4), tapi TIDAK boleh error permission
SELECT sys.fn_cdc_get_max_lsn();          -- harus jalan tanpa error
```

## 2. PostgreSQL — 🐧 DOCKER, via `psql`

### 2a. Cek dulu sebelum bikin apa pun

```bash
sudo -u postgres psql
```

```sql
-- role migration_user sudah ada belum?
SELECT rolname, rolcanlogin, rolcreatedb, rolsuper
FROM pg_roles
WHERE rolname = 'migration_user';

-- daftar semua role yang ada
\du
```

### 2b. Buat role `migration_user` (sekali saja)

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

Alternatif least-privilege (tanpa `CREATE` di level database — lihat runbook Fase 2a):

```sql
CREATE ROLE migration_user WITH LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_KUAT';
GRANT CONNECT ON DATABASE migratedb TO migration_user;
\connect migratedb
CREATE SCHEMA IF NOT EXISTS solarwinds AUTHORIZATION migration_user;
CREATE SCHEMA IF NOT EXISTS migration_control AUTHORIZATION migration_user;
```

### 2c. Cek user & hak akses setelah dibuat

```sql
\connect migratedb

-- schema apa saja yang dimiliki/bisa diakses migration_user
\dn+

-- hak CREATE di database ini beneran ada?
SELECT has_database_privilege('migration_user', 'migratedb', 'CREATE') AS can_create_schema;
SELECT has_database_privilege('migration_user', 'migratedb', 'CONNECT') AS can_connect;
```

Login test dari shell (bukan dari sesi superuser):

```bash
psql -h 127.0.0.1 -p 5432 -U migration_user -d migratedb -c "SELECT current_user, current_database();"
```

Kalau ini gagal konek (bukan gagal auth, tapi gagal *connect*), itu bukan soal user — cek `pg_hba.conf`/`listen_addresses` di [DEPLOYMENT-RUNBOOK.md](DEPLOYMENT-RUNBOOK.md) Fase 2b (koneksi dari container Docker butuh rule terpisah dari koneksi `127.0.0.1` biasa).
