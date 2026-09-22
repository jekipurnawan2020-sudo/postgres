-- ============================================================================
-- SOLARWINDS DATABASE DISCOVERY & VALIDATION SCRIPT
-- Jalankan di SQL Server (SSMS / sqlcmd) SEBELUM mulai migrasi.
-- Tujuan: mengetahui struktur database SolarWinds Anda yang SEBENARNYA
-- (jumlah tabel, kolom, row count, primary key) sebagai bahan konfigurasi
-- scripts/01-enable-cdc.sql dan scripts/06-generate-postgres-ddl.py.
-- ============================================================================

USE [SolarWindsOrion26];
GO

PRINT '======================================================'
PRINT 'SOLARWINDS DATABASE DISCOVERY'
PRINT '======================================================'
GO

-- 1. TOTAL TABLE COUNT
PRINT ''
PRINT '1. TOTAL TABLES:'
SELECT COUNT(*) AS total_tables
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE';
GO

-- 2. LIST ALL TABLES WITH COLUMN COUNT
PRINT ''
PRINT '2. ALL TABLES:'
SELECT
    t.TABLE_NAME,
    COUNT(c.COLUMN_NAME) AS column_count
FROM INFORMATION_SCHEMA.TABLES t
LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
    ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
ORDER BY t.TABLE_NAME;
GO

-- 3. ROW COUNTS (untuk memperkirakan volume initial load per tabel)
PRINT ''
PRINT '3. ROW COUNTS:'
SELECT
    OBJECT_SCHEMA_NAME(p.object_id) AS SchemaName,
    OBJECT_NAME(p.object_id) AS TableName,
    SUM(p.rows) AS [RowCount]
FROM sys.partitions p
WHERE p.index_id IN (0, 1) AND OBJECTPROPERTY(p.object_id, 'IsUserTable') = 1
GROUP BY p.object_id
ORDER BY SUM(p.rows) DESC;
GO

-- 4. PRIMARY KEY INFORMATION
PRINT ''
PRINT '4. PRIMARY KEY INFORMATION:'
SELECT
    t.TABLE_NAME,
    STRING_AGG(kcu.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY kcu.ORDINAL_POSITION) AS PrimaryKeyColumns
FROM INFORMATION_SCHEMA.TABLES t
JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    ON tc.TABLE_NAME = t.TABLE_NAME AND tc.TABLE_SCHEMA = t.TABLE_SCHEMA AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
ORDER BY t.TABLE_NAME;
GO

-- 5. TABLES WITHOUT PRIMARY KEY (tidak akan ikut CDC di 01-enable-cdc.sql)
PRINT ''
PRINT '5. TABLES WITHOUT PRIMARY KEY (TIDAK BISA CDC upsert/delete):'
SELECT t.TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES t
WHERE t.TABLE_SCHEMA = 'dbo'
  AND t.TABLE_TYPE = 'BASE TABLE'
  AND NOT EXISTS (
      SELECT 1
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
      WHERE tc.TABLE_NAME = t.TABLE_NAME AND tc.TABLE_SCHEMA = t.TABLE_SCHEMA AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
  )
ORDER BY t.TABLE_NAME;
GO

-- 6. DATA TYPES YANG DIPAKAI (untuk cek tipe "eksotis" seperti xml, sql_variant,
--    geography/geometry, hierarchyid yang perlu perhatian khusus saat konversi)
PRINT ''
PRINT '6. DISTINCT DATA TYPES IN USE:'
SELECT DATA_TYPE, COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS c
JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY DATA_TYPE
ORDER BY column_count DESC;
GO

PRINT ''
PRINT 'Discovery complete. Gunakan hasil ini untuk scripts/06-generate-postgres-ddl.py'
GO
