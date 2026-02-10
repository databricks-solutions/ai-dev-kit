---
name: uc-abac-governance
description: "Unity Catalog ABAC policy governance - governed tags, masking UDFs, column masks, row filters, and human-in-the-loop policy management."
---

# Unity Catalog ABAC Policy Governance

Guidance for Attribute-Based Access Control (ABAC) policies in Databricks Unity Catalog. Covers governed tags, tag assignments, masking UDFs, CREATE/DROP POLICY syntax, and the human-in-the-loop governance workflow.

**Databricks Docs:**
- ABAC overview: https://docs.databricks.com/data-governance/unity-catalog/abac/
- ABAC policies: https://docs.databricks.com/data-governance/unity-catalog/abac/policies
- ABAC tutorial: https://docs.databricks.com/data-governance/unity-catalog/abac/tutorial

## When to Use This Skill

Use this skill when:
- Creating or managing **ABAC policies** (column masks, row filters)
- Working with **governed tags** (creating via UI, applying via SQL)
- Building **masking UDFs** for PII protection (SSN, email, credit card, etc.)
- Implementing **human-in-the-loop governance** workflows
- Querying tag assignments via `information_schema`
- Managing policy lifecycle (create, update, delete, preview)

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| SQL Generation | [sql-generation.md](sql-generation.md) | SET/UNSET TAG, CREATE FUNCTION, CREATE/DROP POLICY, discovery queries |
| Python SDK | [python-sdk-patterns.md](python-sdk-patterns.md) | `w.policies.*` SDK methods for ABAC policy CRUD |
| MCP Tools | [mcp-tools-reference.md](mcp-tools-reference.md) | 12 MCP tools for policy management |

---

## ABAC Workflow Overview

ABAC policies in Databricks follow a 4-step setup:

1. **Governed Tags** - Define classification taxonomy (UI only)
2. **Tag Assignments** - Apply tags to columns/tables via SQL
3. **Masking UDFs** - Create deterministic functions for data masking
4. **ABAC Policies** - Bind tags to UDFs with principal scoping

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Governed Tags│───>│    Tag       │───>│  Masking     │───>│    ABAC      │
│ (UI only)    │    │ Assignments  │    │    UDFs      │    │  Policies    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

---

## IMPORTANT: SQL That Does NOT Exist

These SQL commands do **not** exist in Databricks. Do not generate them.

| Invalid SQL | What to use instead |
|---|---|
| `SHOW POLICIES` | REST API: `w.policies.list_policies()` |
| `DESCRIBE POLICY` | REST API: `w.policies.get_policy()` |
| `ALTER POLICY` | Drop and recreate the policy |
| `ALTER USER SET ATTRIBUTES` | SCIM API for user attributes |
| `SHOW USER ATTRIBUTES` | SCIM API for user attributes |

---

## Step 1: Governed Tags

Governed tags **cannot** be created via SQL. They must be created in the Databricks UI.

### Creating a Governed Tag (UI Steps)

1. Navigate to **Catalog** in the workspace
2. Select **Governed Tags** from the left panel
3. Click **Create governed tag**
4. Configure:
   - **Tag Key**: e.g., `pii_type`
   - **Allowed Values**: e.g., `ssn`, `email`, `phone`, `credit_card`, `address`
   - **Description**: e.g., "PII classification for ABAC policies"

> **Note:** Tag data is stored as plain text and may be replicated globally. Avoid sensitive information in tag names or values.

**Docs:** https://docs.databricks.com/admin/governed-tags/

---

## Step 2: Applying Tags to Columns

### Legacy Syntax (all versions)

```sql
-- Set tag on column
ALTER TABLE catalog.schema.table
ALTER COLUMN column_name SET TAGS ('pii_type' = 'ssn');

-- Set tag on table
ALTER TABLE catalog.schema.table
SET TAGS ('data_classification' = 'confidential');

-- Remove tag
ALTER TABLE catalog.schema.table
ALTER COLUMN column_name UNSET TAGS ('pii_type');
```

### Modern Syntax (DBR 16.1+)

```sql
SET TAG ON COLUMN catalog.schema.table.column_name 'pii_type' = 'ssn';
SET TAG ON TABLE catalog.schema.table 'data_classification' = 'confidential';
SET TAG ON SCHEMA catalog.schema 'environment' = 'production';
SET TAG ON CATALOG catalog 'department' = 'finance';

UNSET TAG ON COLUMN catalog.schema.table.column_name 'pii_type';
```

### Querying Existing Tags

```sql
-- Column tags
SELECT tag_name, tag_value, column_name
FROM system.information_schema.column_tags
WHERE catalog_name = 'my_catalog'
  AND schema_name = 'my_schema'
  AND table_name = 'my_table';

-- Table tags
SELECT tag_name, tag_value
FROM system.information_schema.table_tags
WHERE catalog_name = 'my_catalog'
  AND schema_name = 'my_schema'
  AND table_name = 'my_table';
```

---

## Step 3: Masking UDFs

Masking UDFs must be `DETERMINISTIC` and use simple `CASE` statements. No external calls or nested UDFs.

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

-- SSN mask: ***-**-XXXX format
CREATE OR REPLACE FUNCTION catalog.schema.mask_ssn(ssn STRING)
RETURNS STRING
DETERMINISTIC
COMMENT 'Masks SSN showing only last 4 digits'
RETURN CASE
    WHEN ssn IS NULL THEN NULL
    WHEN LENGTH(REGEXP_REPLACE(ssn, '[^0-9]', '')) >= 4
        THEN CONCAT('***-**-', RIGHT(REGEXP_REPLACE(ssn, '[^0-9]', ''), 4))
    ELSE '***-**-****'
END;

-- Email mask: j***@example.com
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
```

**Docs:** https://docs.databricks.com/data-governance/unity-catalog/abac/udf-best-practices

---

## Step 4: ABAC Policies

### Column Mask Policy

```sql
CREATE OR REPLACE POLICY mask_pii_columns
ON SCHEMA catalog.schema
COMMENT 'Mask PII columns for analysts'
COLUMN MASK catalog.schema.mask_partial
TO `analysts`, `data_scientists`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTagValue('pii_type', 'ssn') AS masked_col
ON COLUMN masked_col;
```

### Row Filter Policy

```sql
CREATE OR REPLACE POLICY filter_eu_rows
ON CATALOG my_catalog
COMMENT 'Filter EU rows for US team'
ROW FILTER catalog.schema.is_not_eu_region
TO `us_team`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTagValue('region', 'eu') AS filter_col
USING COLUMNS (filter_col);
```

### Drop Policy

```sql
DROP POLICY mask_pii_columns ON SCHEMA catalog.schema;
```

### CRITICAL: Always Exclude `gov_admin`

Every ABAC policy **MUST** include `EXCEPT \`gov_admin\`` to protect administrator access. Without this, admins could be locked out of data.

### Policy Quotas

| Scope | Max Policies |
|-------|-------------|
| Per Catalog | 10 |
| Per Schema | 10 |
| Per Table | 5 |

---

## Human-in-the-Loop Governance Workflow

ABAC policy changes should follow a governed workflow:

```
ANALYZE → RECOMMEND → PREVIEW → APPROVE → EXECUTE → VERIFY
   │          │          │          │          │         │
   ▼          ▼          ▼          ▼          ▼         ▼
 Discover  Generate   Show SQL   Human     Run SQL   Confirm
 current   policy     & impact   confirms  or SDK    changes
 state     proposals  preview    changes   call      applied
```

1. **ANALYZE**: Discover current tags, policies, and UDFs
2. **RECOMMEND**: Generate policy proposals based on requirements
3. **PREVIEW**: Use `preview_policy_changes` to show exact SQL and impact
4. **APPROVE**: Human reviews and explicitly approves
5. **EXECUTE**: Create/update/delete policies via SDK or SQL
6. **VERIFY**: Confirm policies are applied correctly

**Never auto-execute policy changes.** Always preview and wait for human approval.

---

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `POLICY_QUOTA_EXCEEDED` | Too many policies on scope | Consolidate policies or use broader scope |
| `INVALID_TAG_VALUE` | Tag value not in governed tag's allowed values | Check governed tag configuration in UI |
| `UDF_NOT_FOUND` | Masking UDF doesn't exist | Create UDF first, use fully qualified name |
| `POLICY_ALREADY_EXISTS` | Policy name conflict | Use `CREATE OR REPLACE POLICY` |
| `INSUFFICIENT_PERMISSIONS` | Missing `MANAGE` on securable | Grant `MANAGE` permission to policy creator |
| `SHOW POLICIES is not supported` | Used invalid SQL | Use REST API `w.policies.list_policies()` instead |

## Best Practices

1. **Use governed tags** (not ad-hoc tags) for ABAC policy matching
2. **Always include `EXCEPT \`gov_admin\``** in every policy
3. **Use deterministic UDFs** with simple CASE statements
4. **Preview before executing** any policy change
5. **Start at schema scope** and narrow to table only when needed
6. **Name policies descriptively**: `mask_{what}_{scope}` or `filter_{what}_{scope}`
7. **Test UDFs independently** before binding to policies
8. **Monitor policy quotas** — consolidate when approaching limits

## Resources

- [ABAC Overview](https://docs.databricks.com/data-governance/unity-catalog/abac/)
- [ABAC Policies](https://docs.databricks.com/data-governance/unity-catalog/abac/policies)
- [ABAC Tutorial](https://docs.databricks.com/data-governance/unity-catalog/abac/tutorial)
- [UDF Best Practices](https://docs.databricks.com/data-governance/unity-catalog/abac/udf-best-practices)
- [Governed Tags](https://docs.databricks.com/admin/governed-tags/)
- [Column Masks & Row Filters](https://docs.databricks.com/data-governance/unity-catalog/filters-and-masks/)
