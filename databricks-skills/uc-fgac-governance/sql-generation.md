# SQL Generation Reference

Pure SQL patterns for Unity Catalog ABAC governance operations. All SQL follows Databricks syntax.

---

## Tag Operations

### SET TAG on Column

```sql
-- Legacy syntax (all versions)
ALTER TABLE catalog.schema.table
ALTER COLUMN column_name SET TAGS ('pii_type' = 'ssn');

-- Modern syntax (DBR 16.1+)
SET TAG ON COLUMN catalog.schema.table.column_name 'pii_type' = 'ssn';
```

### SET TAG on Table

```sql
-- Legacy syntax
ALTER TABLE catalog.schema.table
SET TAGS ('data_classification' = 'confidential');

-- Modern syntax
SET TAG ON TABLE catalog.schema.table 'data_classification' = 'confidential';
```

### SET TAG on Schema / Catalog

```sql
SET TAG ON SCHEMA catalog.schema 'environment' = 'production';
SET TAG ON CATALOG my_catalog 'department' = 'finance';
```

### UNSET TAG

```sql
-- Column (legacy)
ALTER TABLE catalog.schema.table
ALTER COLUMN column_name UNSET TAGS ('pii_type');

-- Column (modern)
UNSET TAG ON COLUMN catalog.schema.table.column_name 'pii_type';

-- Table (legacy)
ALTER TABLE catalog.schema.table
UNSET TAGS ('data_classification');

-- Table (modern)
UNSET TAG ON TABLE catalog.schema.table 'data_classification';
```

**Docs:**
- SET TAG: https://docs.databricks.com/sql/language-manual/sql-ref-syntax-ddl-set-tag.html
- UNSET TAG: https://docs.databricks.com/sql/language-manual/sql-ref-syntax-ddl-unset-tag.html

---

## Tag Discovery Queries

### Query Column Tags

```sql
SELECT tag_name, tag_value, column_name
FROM system.information_schema.column_tags
WHERE catalog_name = 'my_catalog'
  AND schema_name = 'my_schema'
  AND table_name = 'my_table';
```

### Query Table Tags

```sql
SELECT tag_name, tag_value
FROM system.information_schema.table_tags
WHERE catalog_name = 'my_catalog'
  AND schema_name = 'my_schema'
  AND table_name = 'my_table';
```

### All Tag Assignments in a Catalog

```sql
-- Table-level tags
SELECT 'TABLE' as securable_type,
       CONCAT(catalog_name, '.', schema_name, '.', table_name) as securable_name,
       tag_name as tag_key,
       tag_value
FROM system.information_schema.table_tags
WHERE catalog_name = 'my_catalog';

-- Column-level tags
SELECT 'COLUMN' as securable_type,
       CONCAT(catalog_name, '.', schema_name, '.', table_name, '.', column_name) as securable_name,
       tag_name as tag_key,
       tag_value
FROM system.information_schema.column_tags
WHERE catalog_name = 'my_catalog';
```

**Docs:**
- information_schema.column_tags: https://docs.databricks.com/sql/language-manual/information-schema/column_tags.html
- information_schema.table_tags: https://docs.databricks.com/sql/language-manual/information-schema/table_tags.html

---

## Masking UDF Creation

All masking UDFs must be `DETERMINISTIC` with simple `CASE` statements. No external calls or nested UDFs.

### Generic Masking Strategies

```sql
-- Full mask: replaces all characters with *
CREATE OR REPLACE FUNCTION catalog.schema.mask_full(value STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Full masking - replaces all characters with *'
RETURN CASE
    WHEN value IS NULL THEN NULL
    ELSE REPEAT('*', LENGTH(value))
END;

-- Partial mask: show last 4 characters
CREATE OR REPLACE FUNCTION catalog.schema.mask_partial(value STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Partial masking - shows last 4 characters'
RETURN CASE
    WHEN value IS NULL THEN NULL
    WHEN LENGTH(value) <= 4 THEN REPEAT('*', LENGTH(value))
    ELSE CONCAT(REPEAT('*', LENGTH(value) - 4), RIGHT(value, 4))
END;

-- Hash: SHA256 with version prefix
CREATE OR REPLACE FUNCTION catalog.schema.mask_hash(value STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Hash masking - SHA256 with version prefix'
RETURN CASE
    WHEN value IS NULL THEN NULL
    ELSE CONCAT('HASH_v1_', SUBSTRING(SHA2(CONCAT(value, ':v1'), 256), 1, 16))
END;

-- Redact: replace with [REDACTED]
CREATE OR REPLACE FUNCTION catalog.schema.mask_redact(value STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Redaction - replaces value with [REDACTED]'
RETURN CASE
    WHEN value IS NULL THEN NULL
    ELSE '[REDACTED]'
END;

-- Nullify: always returns NULL
CREATE OR REPLACE FUNCTION catalog.schema.mask_nullify(value STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Nullify - always returns NULL'
RETURN NULL;
```

### Specialized Masking UDFs

```sql
-- SSN: ***-**-XXXX
CREATE OR REPLACE FUNCTION catalog.schema.mask_ssn(ssn STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Masks SSN showing only last 4 digits in XXX-XX-XXXX format'
RETURN CASE
    WHEN ssn IS NULL THEN NULL
    WHEN LENGTH(REGEXP_REPLACE(ssn, '[^0-9]', '')) >= 4
        THEN CONCAT('***-**-', RIGHT(REGEXP_REPLACE(ssn, '[^0-9]', ''), 4))
    ELSE '***-**-****'
END;

-- Email: j***@example.com
CREATE OR REPLACE FUNCTION catalog.schema.mask_email(email STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Masks email showing first char and domain'
RETURN CASE
    WHEN email IS NULL THEN NULL
    WHEN INSTR(email, '@') > 1
        THEN CONCAT(LEFT(email, 1), '***@', SUBSTRING(email, INSTR(email, '@') + 1))
    ELSE '***@***.***'
END;

-- Credit card: ****-****-****-1234
CREATE OR REPLACE FUNCTION catalog.schema.mask_credit_card(card_number STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Masks credit card showing only last 4 digits'
RETURN CASE
    WHEN card_number IS NULL THEN NULL
    WHEN LENGTH(REGEXP_REPLACE(card_number, '[^0-9]', '')) >= 4
        THEN CONCAT('****-****-****-', RIGHT(REGEXP_REPLACE(card_number, '[^0-9]', ''), 4))
    ELSE '****-****-****-****'
END;
```

### Row Filter UDFs

Row filter UDFs return `BOOLEAN`: `TRUE` to include, `FALSE` to exclude.

```sql
-- Region-based filter: hide EU rows
CREATE OR REPLACE FUNCTION catalog.schema.is_not_eu_region(region_value STRING)
RETURNS BOOLEAN
DETERMINISTIC
COMMENT 'Row filter - returns FALSE for EU regions'
RETURN CASE
    WHEN region_value IS NULL THEN TRUE
    WHEN LOWER(region_value) LIKE '%eu%' THEN FALSE
    WHEN LOWER(region_value) LIKE '%europe%' THEN FALSE
    ELSE TRUE
END;

-- Array membership filter
CREATE OR REPLACE FUNCTION catalog.schema.is_in_allowed_values(
    row_value STRING,
    allowed_values ARRAY<STRING>
)
RETURNS BOOLEAN
DETERMINISTIC
COMMENT 'Row filter based on array membership'
RETURN CASE
    WHEN allowed_values IS NULL THEN FALSE
    WHEN ARRAY_CONTAINS(TRANSFORM(allowed_values, x -> LOWER(x)), LOWER(row_value)) THEN TRUE
    ELSE FALSE
END;
```

**Docs:** https://docs.databricks.com/data-governance/unity-catalog/abac/udf-best-practices

---

## Policy Creation

### Column Mask Policy

```sql
CREATE OR REPLACE POLICY mask_pii_ssn
ON SCHEMA catalog.schema
COMMENT 'Mask SSN columns for analysts'
COLUMN MASK catalog.schema.mask_ssn
TO `analysts`, `data_scientists`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTagValue('pii_type', 'ssn') AS masked_col
ON COLUMN masked_col;
```

### Row Filter Policy

```sql
CREATE OR REPLACE POLICY filter_eu_data
ON CATALOG my_catalog
COMMENT 'Filter EU rows for US team'
ROW FILTER catalog.schema.is_not_eu_region
TO `us_team`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTagValue('region', 'eu') AS filter_col
USING COLUMNS (filter_col);
```

### Policy with Tag Key Only (any value)

```sql
-- Match any column with tag 'pii_type' regardless of value
CREATE OR REPLACE POLICY mask_all_pii
ON SCHEMA catalog.schema
COLUMN MASK catalog.schema.mask_full
TO `external_users`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTag('pii_type') AS masked_col
ON COLUMN masked_col;
```

### Drop Policy

```sql
DROP POLICY mask_pii_ssn ON SCHEMA catalog.schema;
DROP POLICY filter_eu_data ON CATALOG my_catalog;
```

> **Note:** There is no `ALTER POLICY`. To modify a policy, drop and recreate it.

---

## Discovery Queries

```sql
-- List catalogs
SHOW CATALOGS;

-- List schemas in a catalog
SHOW SCHEMAS IN my_catalog;

-- List tables in a schema
SHOW TABLES IN my_catalog.my_schema;

-- Describe table with extended metadata
DESCRIBE TABLE EXTENDED my_catalog.my_schema.my_table;

-- List UDFs in a schema
SHOW USER FUNCTIONS IN my_catalog.my_schema;

-- Describe a UDF
DESCRIBE FUNCTION EXTENDED my_catalog.my_schema.mask_ssn;

-- Sample column values
SELECT DISTINCT column_name
FROM my_catalog.my_schema.my_table
LIMIT 20;
```

---

## Enums Reference

### PII Types (governed tag values)

`ssn`, `email`, `phone`, `credit_card`, `date_of_birth`, `address`, `name`, `ip_address`, `national_id`, `medical_record`, `generic`

### Masking Strategies

| Strategy | Description |
|----------|-------------|
| `full_mask` | Replace all characters with `*` |
| `partial_mask` | Show last 4 characters |
| `hash` | SHA256 with version prefix |
| `redact` | Replace with `[REDACTED]` |
| `nullify` | Always return NULL |
| `custom` | User-supplied SQL (requires manual UDF) |

### Policy Scopes

| Scope | Description |
|-------|-------------|
| `CATALOG` | Policy applies to all tables in catalog |
| `SCHEMA` | Policy applies to all tables in schema |
| `TABLE` | Policy applies to a single table |

### Tag Syntax Variants

| Variant | Availability | Example |
|---------|-------------|---------|
| `LEGACY` | All versions | `ALTER TABLE t ALTER COLUMN c SET TAGS ('k'='v')` |
| `MODERN` | DBR 16.1+ | `SET TAG ON COLUMN t.c 'k' = 'v'` |
