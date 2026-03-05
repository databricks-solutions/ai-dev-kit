# Tags & Classification

Tag Unity Catalog objects and columns for governance, data discovery, and compliance tracking.

## MCP Tool

| Tool | Purpose |
|------|---------|
| `manage_uc_tags` | Set/unset tags, set comments, query tags from system tables |

---

## Setting Tags

Tags are key-value pairs attached to catalogs, schemas, tables, or columns.

### Tag a Table

```python
manage_uc_tags(
    action="set_tags",
    object_type="table",
    full_name="analytics.gold.customers",
    tags={"pii": "true", "classification": "confidential", "owner_team": "data-eng"}
)
```

### Tag a Column

```python
manage_uc_tags(
    action="set_tags",
    object_type="column",
    full_name="analytics.gold.customers",
    column_name="email",
    tags={"pii": "true", "data_type": "email_address"}
)
```

### Tag a Catalog or Schema

```python
manage_uc_tags(
    action="set_tags",
    object_type="catalog",
    full_name="analytics",
    tags={"environment": "production", "cost_center": "CC-1234"}
)
```

---

## Removing Tags

```python
manage_uc_tags(
    action="unset_tags",
    object_type="table",
    full_name="analytics.gold.customers",
    tag_names=["classification", "owner_team"]
)
```

---

## Setting Comments

```python
manage_uc_tags(
    action="set_comment",
    object_type="table",
    full_name="analytics.gold.customers",
    comment_text="Master customer table. Updated daily via SDP pipeline."
)

# Comment on a column
manage_uc_tags(
    action="set_comment",
    object_type="column",
    full_name="analytics.gold.customers",
    column_name="customer_id",
    comment_text="Unique customer identifier. FK to orders.customer_id."
)
```

---

## Querying Tags

### Find All Tagged Tables

```python
manage_uc_tags(
    action="query_table_tags",
    catalog_filter="analytics"
)
# Returns rows from system.information_schema.table_tags
```

### Find PII Tables

```python
manage_uc_tags(
    action="query_table_tags",
    tag_name_filter="pii",
    tag_value_filter="true"
)
```

### Find Tagged Columns

```python
manage_uc_tags(
    action="query_column_tags",
    catalog_filter="analytics",
    tag_name_filter="pii"
)
```

### Filter by Table

```python
manage_uc_tags(
    action="query_column_tags",
    catalog_filter="analytics",
    table_name_filter="customers"
)
```

---

## Common Tagging Patterns

### PII Classification

```python
pii_columns = {
    "analytics.gold.customers": ["email", "phone", "ssn", "address"],
    "analytics.gold.employees": ["email", "salary", "ssn"],
}

for table, columns in pii_columns.items():
    manage_uc_tags(action="set_tags", object_type="table",
                   full_name=table, tags={"contains_pii": "true"})
    for col in columns:
        manage_uc_tags(action="set_tags", object_type="column",
                       full_name=table, column_name=col,
                       tags={"pii": "true"})
```

### Data Domain Tagging

```python
manage_uc_tags(action="set_tags", object_type="schema",
               full_name="analytics.gold",
               tags={"domain": "analytics", "sla": "99.9%", "refresh": "daily"})
```

### Cost Attribution

```python
manage_uc_tags(action="set_tags", object_type="catalog",
               full_name="ml_features",
               tags={"cost_center": "ML-OPS", "budget_owner": "ml-team@company.com"})
```

---

## Using Tags with System Tables

Tags stored via the MCP tool are queryable through `system.information_schema`:

```sql
-- Find all PII tables across all catalogs
SELECT catalog_name, schema_name, table_name, tag_value
FROM system.information_schema.table_tags
WHERE tag_name = 'pii' AND tag_value = 'true';

-- Find all PII columns
SELECT catalog_name, schema_name, table_name, column_name, tag_value
FROM system.information_schema.column_tags
WHERE tag_name = 'pii';

-- Cross-reference: tables tagged PII but missing column masks
SELECT t.catalog_name, t.schema_name, t.table_name
FROM system.information_schema.table_tags t
LEFT JOIN system.information_schema.column_tags c
  ON t.catalog_name = c.catalog_name
  AND t.schema_name = c.schema_name
  AND t.table_name = c.table_name
  AND c.tag_name = 'masked'
WHERE t.tag_name = 'pii' AND t.tag_value = 'true'
  AND c.tag_name IS NULL;
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Tag query returns empty** | Tags are per-catalog; ensure `catalog_filter` matches. System tables require `system.information_schema` access |
| **"Cannot set tag"** | Need `APPLY_TAG` privilege on the object, plus `USE_CATALOG` and `USE_SCHEMA` |
| **Tag not visible in UI** | Tags set via API/MCP appear in Catalog Explorer under the object's "Tags" tab. Allow a few seconds for propagation |
| **Too many tags** | Maximum 50 tags per object. Use structured naming conventions (e.g., `domain:`, `compliance:`) |
