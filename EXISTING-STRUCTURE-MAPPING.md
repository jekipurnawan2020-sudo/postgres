# FILE MAPPING - SESUAI STRUKTUR EXISTING ANDA

Dokumen ini show **EXACTLY** file mana yang replace/add ke mana dalam struktur yang SUDAH ADA.

---

## STRUKTUR EXISTING ANDA (From Screenshot)

```
solarwinds-migration/
├── cdc/
│   ├── app/
│   │   ├── cdc_reader.py          ✅ KEEP/UPDATE
│   │   ├── checkpoint.py          ✅ KEEP/UPDATE
│   │   ├── config.py              ✅ UPDATE (important!)
│   │   ├── initial_load.py        ✅ KEEP/UPDATE
│   │   ├── main.py                ✅ KEEP/UPDATE
│   │   ├── metadata.py            ✅ KEEP (your custom file)
│   │   ├── producer.py            ✅ KEEP/UPDATE
│   │   ├── schema_builder.py      ✅ KEEP/UPDATE
│   │   ├── sqlserver.py           ✅ KEEP/UPDATE
│   │   ├── topic_manager.py       ✅ KEEP/UPDATE
│   │   └── utils.py               ✅ KEEP/UPDATE
│   ├── Dockerfile                 ✅ UPDATE
│   └── requirements.txt           ✅ UPDATE
│
├── connect/
│   ├── Dockerfile                 ✅ UPDATE
│   └── connectors/
│       ├── generate_connectors.py ✅ KEEP (your custom file)
│       └── postgres-sink.json     ✅ KEEP
│
├── logs/
│   └── .gitkeep                   ✅ KEEP
│
├── scripts/
│   ├── 00-discovery-database.sql  ➕ ADD NEW
│   ├── 01-enable-cdc.sql          ✅ UPDATE
│   ├── 02-check-tables.sql        ✅ UPDATE
│   ├── 03-check-primary-keys.sql  ✅ KEEP or REPLACE with 03-verify-cdc.sql
│   ├── 04-check-cdc.sql           ✅ UPDATE
│   └── 05-create-postgres-control.sql ✅ UPDATE
│
├── .env                           ✅ UPDATE
├── .gitignore                     ✅ UPDATE
├── docker-compose.yml             ✅ UPDATE
├── phase-ars.md                   ✅ KEEP (your existing doc)
└── README.md                      ✅ UPDATE
```

---

## FILE PLACEMENT GUIDE

### ✅ FILES TO KEEP (Your Existing, No Changes)
```
cdc/app/metadata.py                (your custom metadata module)
connect/connectors/generate_connectors.py    (your custom generator)
connect/connectors/postgres-sink.json        (your config)
logs/.gitkeep                      (keep as is)
phase-ars.md                       (your existing doc)
```

**ACTION**: No changes needed, keep these files as-is.

---

### ✅ FILES TO UPDATE/REPLACE (Better Versions)

#### 1. **cdc/app/** (Python Application)
```
REPLACE dengan:
├── cdc_reader.py          ← From generated files
├── checkpoint.py          ← From generated files
├── config.py              ← CRITICAL! Update with your actual tables
├── initial_load.py        ← From generated files
├── main.py                ← From generated files
├── producer.py            ← From generated files
├── schema_builder.py      ← From generated files
├── sqlserver.py           ← From generated files
├── topic_manager.py       ← From generated files
└── utils.py               ← From generated files
```

**ACTION**:
```bash
# Copy these files dari output saya ke cdc/app/
cp cdc_reader.py cdc/app/
cp checkpoint.py cdc/app/
cp config.py cdc/app/
cp initial_load.py cdc/app/
cp main.py cdc/app/
cp producer.py cdc/app/
cp schema_builder.py cdc/app/
cp sqlserver.py cdc/app/
cp topic_manager.py cdc/app/
cp utils.py cdc/app/

# JANGAN overwrite metadata.py (your custom file)
```

---

#### 2. **cdc/ Container Files**
```
REPLACE dengan:
├── Dockerfile        ← From generated Dockerfile.cdc
└── requirements.txt  ← From generated requirements.txt
```

**ACTION**:
```bash
cp Dockerfile.cdc cdc/Dockerfile
cp requirements.txt cdc/requirements.txt
```

---

#### 3. **connect/ Container**
```
REPLACE:
└── Dockerfile       ← From generated Dockerfile.connect
```

**ACTION**:
```bash
cp Dockerfile.connect connect/Dockerfile

# KEEP: connectors/ folder & files as-is
```

---

#### 4. **scripts/ SQL Scripts**
```
KEEP existing:
├── 01-enable-cdc.sql
├── 02-check-tables.sql
├── 04-check-cdc.sql
└── 05-create-postgres-control.sql

REPLACE:
├── 03-check-primary-keys.sql  ← or remove, not critical
└── 04-check-cdc.sql           ← optional, replace dengan 03-verify-cdc.sql

ADD NEW:
└── 00-discovery-database.sql  ← IMPORTANT! Add this first
```

**ACTION**:
```bash
# ADD this new file
cp 00-discovery-database.sql scripts/

# REPLACE optional:
# cp 03-verify-cdc.sql scripts/03-verify-cdc.sql
# atau keep yang existing

# KEEP: 01, 02, 04, 05 as-is atau update untuk better versions
```

---

#### 5. **Root Configuration Files**
```
REPLACE:
├── docker-compose.yml  ← Updated version
├── .env               ← Update with password!
├── .gitignore         ← Better version
└── README.md          ← Comprehensive version
```

**ACTION**:
```bash
cp docker-compose.yml .
cp .env .             # EDIT this with actual SQL password!
cp .gitignore .
cp README.md .
```

---

### ➕ FILES TO ADD (Optional but Recommended)

Ini OPTIONAL, untuk reference & documentation saja:

```
➕ docs/                          (NEW directory - optional)
  ├── SOLARWINDS-DATABASE-REFERENCE.md   (baseline schema info)
  └── VALIDATION-CHECKLIST.md            (validation guide)

➕ setup.sh                       (Quick setup script - root)
➕ monitor.sh                     (Monitoring script - root)
➕ config-template.py            (Reference template - cdc/app/)
```

**ACTION** (If you want these):
```bash
# Create docs directory
mkdir -p docs

# Copy optional files
cp SOLARWINDS-DATABASE-REFERENCE.md docs/
cp VALIDATION-CHECKLIST.md docs/
cp setup.sh .
cp monitor.sh .
cp config-template.py cdc/app/
chmod +x setup.sh monitor.sh
```

---

## QUICK COPY COMMANDS

Jika sudah download semua file dari saya, jalankan ini (update paths as needed):

```bash
#!/bin/bash
# auto-update.sh - Run dari root folder project Anda

echo "Updating files sesuai struktur existing..."

# 1. Update cdc/app files
cp cdc_reader.py cdc/app/
cp checkpoint.py cdc/app/
cp config.py cdc/app/
cp initial_load.py cdc/app/
cp main.py cdc/app/
cp producer.py cdc/app/
cp schema_builder.py cdc/app/
cp sqlserver.py cdc/app/
cp topic_manager.py cdc/app/
cp utils.py cdc/app/

# 2. Update container files
cp Dockerfile.cdc cdc/Dockerfile
cp Dockerfile.connect connect/Dockerfile
cp requirements.txt cdc/

# 3. Update SQL scripts
cp 00-discovery-database.sql scripts/
cp 01-enable-cdc.sql scripts/
cp 02-check-tables.sql scripts/
cp 03-verify-cdc.sql scripts/03-verify-cdc.sql
cp 04-create-postgres-control.sql scripts/

# 4. Update root files
cp docker-compose.yml .
cp .env .
cp .gitignore .
cp README.md .

# 5. Optional: Add setup scripts
cp setup.sh .
cp monitor.sh .
chmod +x setup.sh monitor.sh

# 6. Optional: Add docs & templates
mkdir -p docs
cp SOLARWINDS-DATABASE-REFERENCE.md docs/
cp VALIDATION-CHECKLIST.md docs/
cp config-template.py cdc/app/

echo "✓ Files updated!"
echo ""
echo "NEXT STEPS:"
echo "1. Edit .env dengan SQL Server password"
echo "2. Edit cdc/app/config.py dengan actual tables"
echo "3. Run: docker-compose up -d"
echo "4. Monitor: docker-compose logs -f cdc-producer"
```

---

## CRITICAL: MOST IMPORTANT FILE

**🔴 cdc/app/config.py** - MUST BE CUSTOMIZED!

```python
# Setelah run scripts/00-discovery-database.sql di SQL Server
# Update config.py dengan actual tables Anda

SOLARWINDS_TABLES = [
    "dbo.Nodes",           # Change these ke tabel actual Anda!
    "dbo.Interfaces",
    "dbo.InterfaceTraffic",
    # ... dst sesuai database Anda
]
```

Tanpa update ini, migration akan FAIL karena table tidak ditemukan.

---

## SUMMARY TABLE

| File | Location | Action | Priority |
|------|----------|--------|----------|
| 00-discovery-database.sql | scripts/ | ADD | 🔴 CRITICAL |
| config.py | cdc/app/ | UPDATE | 🔴 CRITICAL |
| .env | root | UPDATE (password) | 🔴 CRITICAL |
| docker-compose.yml | root | REPLACE | 🟡 Important |
| All .py files | cdc/app/ | REPLACE | 🟡 Important |
| Dockerfile (both) | cdc/, connect/ | REPLACE | 🟡 Important |
| scripts/*.sql | scripts/ | REPLACE/ADD | 🟡 Important |
| README.md | root | REPLACE | 🟢 Good to have |
| setup.sh | root | ADD | 🟢 Good to have |
| monitor.sh | root | ADD | 🟢 Good to have |
| metadata.py | cdc/app/ | KEEP | ✅ Your file |
| generate_connectors.py | connect/connectors/ | KEEP | ✅ Your file |
| phase-ars.md | root | KEEP | ✅ Your file |

---

## FINAL VERIFICATION

Setelah selesai update, struktur Anda should look seperti ini:

```
solarwinds-migration/
├── cdc/
│   ├── app/
│   │   ├── main.py                    ✅ Updated
│   │   ├── config.py                  ✅ Updated + Customized for YOUR tables
│   │   ├── sqlserver.py               ✅ Updated
│   │   ├── initial_load.py            ✅ Updated
│   │   ├── cdc_reader.py              ✅ Updated
│   │   ├── producer.py                ✅ Updated
│   │   ├── checkpoint.py              ✅ Updated
│   │   ├── schema_builder.py          ✅ Updated
│   │   ├── topic_manager.py           ✅ Updated
│   │   ├── utils.py                   ✅ Updated
│   │   ├── metadata.py                ✅ Your file (KEPT)
│   │   └── config-template.py         ➕ Optional reference
│   ├── Dockerfile                     ✅ Updated
│   └── requirements.txt               ✅ Updated
│
├── connect/
│   ├── Dockerfile                     ✅ Updated
│   └── connectors/
│       ├── generate_connectors.py     ✅ Your file (KEPT)
│       └── postgres-sink.json         ✅ Your config (KEPT)
│
├── logs/
│   └── .gitkeep                       ✅ KEPT
│
├── scripts/
│   ├── 00-discovery-database.sql      ➕ ADD NEW
│   ├── 01-enable-cdc.sql              ✅ Updated
│   ├── 02-check-tables.sql            ✅ Updated
│   ├── 03-verify-cdc.sql              ✅ Updated (replace or rename 03-check-primary-keys.sql)
│   ├── 04-check-cdc.sql               ✅ Updated (rename dari 04-check-cdc.sql)
│   └── 05-create-postgres-control.sql ✅ Updated
│
├── docs/                              ➕ Optional
│   ├── SOLARWINDS-DATABASE-REFERENCE.md
│   └── VALIDATION-CHECKLIST.md
│
├── .env                               ✅ Updated (with YOUR password!)
├── .gitignore                         ✅ Updated
├── docker-compose.yml                 ✅ Updated
├── README.md                          ✅ Updated
├── setup.sh                           ➕ Optional
├── monitor.sh                         ➕ Optional
└── phase-ars.md                       ✅ Your file (KEPT)
```

---

## FINAL CHECKLIST

Sebelum start migration:

- [ ] Updated all .py files di cdc/app/ (keep metadata.py)
- [ ] Updated Dockerfile di cdc/ dan connect/
- [ ] Updated requirements.txt
- [ ] Updated docker-compose.yml
- [ ] Updated .env dengan actual SQL Server password
- [ ] Updated config.py dengan actual table list dari database Anda
- [ ] Added 00-discovery-database.sql ke scripts/
- [ ] Verified struktur sesuai preview di atas
- [ ] Run 00-discovery-database.sql di SQL Server (check berapa tabel)
- [ ] Verify metadata.py & generate_connectors.py intact (your custom files)

Done? Ready untuk start migration!

```bash
docker-compose up -d
docker-compose logs -f cdc-producer
```
