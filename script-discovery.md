-- ============================================================================
-- SOLARWINDS DATABASE DISCOVERY & VALIDATION SCRIPT
-- Add this ke scripts/ folder untuk explore actual database
-- Run di SQL Server sebelum mulai migration
-- ============================================================================

USE solarwinds;
GO

PRINT '======================================================'
PRINT 'SOLARWINDS DATABASE DISCOVERY'
PRINT '======================================================'
GO

-- 1. TOTAL TABLE COUNT
PRINT ''
PRINT '1. TOTAL TABLES:'
SELECT COUNT(*) as total_tables 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE';
GO

-- 2. LIST ALL TABLES WITH COLUMNS
PRINT ''
PRINT '2. ALL TABLES:'
SELECT 
    t.TABLE_NAME,
    COUNT(c.COLUMN_NAME) as column_count
FROM INFORMATION_SCHEMA.TABLES t
LEFT JOIN INFORMATION_SCHEMA.COLUMNS c 
    ON t.TABLE_NAME = c.TABLE_NAME 
WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
ORDER BY t.TABLE_NAME;
GO

-- 3. ROW COUNTS
PRINT ''
PRINT '3. ROW COUNTS:'
SELECT 
    OBJECT_NAME(p.object_id) as TableName,
    SUM(p.rows) as RowCount
FROM sys.partitions p
WHERE p.index_id IN (0, 1) AND OBJECTPROPERTY(p.object_id, 'IsUserTable') = 1
GROUP BY p.object_id
ORDER BY SUM(p.rows) DESC;
GO

-- 4. PRIMARY KEYS
PRINT ''
PRINT '4. PRIMARY KEY INFORMATION:'
SELECT 
    t.TABLE_NAME,
    STRING_AGG(kcu.COLUMN_NAME, ', ') as PrimaryKeyColumns
FROM INFORMATION_SCHEMA.TABLES t
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu 
    ON t.TABLE_NAME = kcu.TABLE_NAME AND kcu.CONSTRAINT_NAME LIKE 'PK_%'
WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE'
GROUP BY t.TABLE_NAME
ORDER BY t.TABLE_NAME;
GO

-- 5. TABLES WITHOUT PRIMARY KEYS
PRINT ''
PRINT '5. TABLES WITHOUT PRIMARY KEYS (ISSUE FOR CDC):'
SELECT t.TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES t
WHERE t.TABLE_SCHEMA = 'dbo' 
  AND NOT EXISTS (
      SELECT 1 FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE TABLE_NAME = t.TABLE_NAME AND CONSTRAINT_NAME LIKE 'PK_%'
  )
ORDER BY t.TABLE_NAME;
GO

PRINT ''
PRINT 'Discovery complete. Use results to update config.py'
GO